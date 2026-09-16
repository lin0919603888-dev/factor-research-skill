"""Load a generated factor module and execute its DataFrame-to-Series function."""

from __future__ import annotations

import argparse
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from typing import Any

import pandas as pd


class FactorExecutionError(RuntimeError):
    """Raised when a factor cannot be safely executed or has an invalid output."""


def _write_factor_module(factor_code: str, directory: Path) -> Path:
    """Materialize generated source as a temporary Python module."""

    path = directory / "generated_factor.py"
    path.write_text(factor_code, encoding="utf-8")
    return path


def _load_function(factor_code: str, function_name: str):
    """Import a generated factor function without installing it as a package."""

    with tempfile.TemporaryDirectory(prefix="factor_execution_") as temp_dir:
        module_path = _write_factor_module(factor_code, Path(temp_dir))
        spec = spec_from_file_location("generated_factor_module", module_path)
        if spec is None or spec.loader is None:
            raise FactorExecutionError("Could not create an import specification.")
        module: ModuleType = module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        function = getattr(module, function_name, None)
        if not callable(function):
            raise FactorExecutionError(f"Function {function_name!r} is not callable.")
        return function


def load_market_data(market_csv: str | Path) -> pd.DataFrame:
    """Load minute CSV and normalize the date column into a datetime index."""

    frame = pd.read_csv(market_csv)
    if "date" not in frame.columns:
        raise FactorExecutionError("Market CSV must contain a date column.")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame = frame.set_index("date", drop=True).sort_index()
    return frame


def execute_factor(factor: dict[str, Any], market_data: pd.DataFrame) -> pd.Series:
    """Execute one factor function and enforce the Series output contract."""

    function_name = factor.get("name")
    factor_code = factor.get("python_code")
    if not isinstance(function_name, str) or not function_name:
        raise FactorExecutionError("Factor JSON is missing a valid name.")
    if not isinstance(factor_code, str) or not factor_code:
        raise FactorExecutionError("Factor JSON is missing python_code.")

    function = _load_function(factor_code, function_name)
    try:
        result = function(market_data.copy())
    except Exception as exc:  # Generated code is intentionally an execution boundary.
        raise FactorExecutionError(f"Factor execution failed: {exc}") from exc

    if not isinstance(result, pd.Series):
        raise FactorExecutionError(
            f"Factor returned {type(result).__name__}; expected pandas.Series."
        )
    if len(result) != len(market_data):
        raise FactorExecutionError(
            f"Factor length {len(result)} does not match input length {len(market_data)}."
        )
    if not result.index.equals(market_data.index):
        result = pd.Series(result.to_numpy(), index=market_data.index, name=function_name)

    numeric = pd.to_numeric(result, errors="coerce").astype(float)
    numeric.name = function_name
    return numeric


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-json", required=True, help="Generated factor JSON.")
    parser.add_argument("--market-csv", required=True, help="Minute-bar market CSV.")
    parser.add_argument("--output-csv", required=True, help="Output factor Series CSV.")
    parser.add_argument("--result-json", help="Optional execution status JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    errors: list[str] = []
    status = "fail"
    try:
        factor = json.loads(Path(args.factor_json).read_text(encoding="utf-8"))
        market = load_market_data(args.market_csv)
        values = execute_factor(factor, market)
        values.to_csv(args.output_csv, index=True, index_label="date", header=True)
        status = "pass"
    except Exception as exc:
        errors.append(str(exc))

    payload = {
        "tool": "factor_executor",
        "status": status,
        "execution": status,
        "output_csv": str(Path(args.output_csv).resolve()) if status == "pass" else None,
        "rows": int(len(values)) if status == "pass" else 0,
        "errors": errors,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.result_json:
        Path(args.result_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

