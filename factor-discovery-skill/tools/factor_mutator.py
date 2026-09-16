"""Create recorded, deterministic mutations of one parent factor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import textwrap
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_common import read_yaml, validate_factor_document, write_yaml  # noqa: E402


OPERATIONS = {
    "scale",
    "sign_flip",
    "difference",
    "rolling_zscore",
    "rolling_rank",
}


def _parent_source(parent: dict[str, Any]) -> str:
    if parent["formula_type"] == "expression":
        return f"base = df.eval(r'''({parent['code']})''')"
    return parent["code"] + f"\n\nbase = {parent['name']}(df)\n"


def _operation_body(operation: str, window: int, parameter: float) -> str:
    if operation == "scale":
        return f"factor = base * {parameter!r}"
    if operation == "sign_flip":
        return "factor = -base"
    if operation == "difference":
        return "factor = base.diff()"
    if operation == "rolling_zscore":
        return (
            f"rolling = base.rolling(window={window}, min_periods=2)\n"
            "factor = (base - rolling.mean()) / rolling.std().replace(0, float('nan'))"
        )
    if operation == "rolling_rank":
        return f"factor = base.rolling(window={window}, min_periods=2).rank(pct=True)"
    raise ValueError(f"Unsupported mutation operation: {operation}")


def mutate_factor(
    parent: dict[str, Any],
    parent_path: str | Path,
    *,
    operation: str = "rolling_zscore",
    reason: str,
    window: int = 20,
    parameter: float = 1.0,
) -> dict[str, Any]:
    """Build a candidate YAML document with explicit parent provenance."""

    if operation not in OPERATIONS:
        raise ValueError(f"Unsupported mutation operation: {operation}.")
    if not reason.strip():
        raise ValueError("A non-empty modification reason is required.")
    if window < 2:
        raise ValueError("window must be at least 2.")
    validation = validate_factor_document(parent)
    if not validation.passed:
        raise ValueError("Parent factor is invalid: " + "; ".join(validation.errors))

    metadata = dict(parent.get("metadata") or {})
    generation = int(metadata.get("generation", 1)) + 1
    operation_suffix = f"mut_{operation}"
    candidate_name = f"{parent['name']}_{operation_suffix}"
    source = _parent_source(parent)
    body = _operation_body(operation, window, parameter)
    code = (
        "import pandas as pd\n\n\n"
        f"def {candidate_name}(df: pd.DataFrame) -> pd.Series:\n"
        f"    {source}\n"
        + textwrap.indent(body, "    ")
        + "\n"
        "    factor.name = "
        f"{candidate_name!r}\n"
        "    return factor.astype(float)\n"
    )
    if operation == "difference" or operation == "rolling_zscore" or operation == "rolling_rank":
        code = code.replace(
            "    factor.name =",
            "    factor = factor.replace([float('inf'), -float('inf')], float('nan'))\n"
            "    factor.name =",
            1,
        )

    return {
        "name": candidate_name,
        "code": code,
        "formula_type": "python",
        "category": parent.get("category", "derived"),
        "description": (
            f"Deterministic {operation} mutation of {parent['name']}. {reason.strip()}"
        ),
        "metadata": {
            "source": "mutation",
            "generation": generation,
            "lineage": {
                "parents": [{
                    "name": parent["name"],
                    "path": str(Path(parent_path).resolve()),
                    "formula_type": parent["formula_type"],
                }],
                "operation": operation,
                "reason": reason.strip(),
                "parameters": {"window": window, "parameter": parameter},
            },
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-yaml", required=True, help="Parent factor YAML.")
    parser.add_argument("--operation", default="rolling_zscore", choices=sorted(OPERATIONS))
    parser.add_argument("--reason", required=True, help="Required research reason for mutation.")
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--parameter", type=float, default=1.0)
    parser.add_argument("--output-yaml", required=True, help="Candidate output YAML.")
    parser.add_argument("--result-json", help="Optional operation result JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        parent = read_yaml(args.factor_yaml)
        candidate = mutate_factor(
            parent,
            args.factor_yaml,
            operation=args.operation,
            reason=args.reason,
            window=args.window,
            parameter=args.parameter,
        )
        write_yaml(candidate, args.output_yaml)
        result = {
            "tool": "factor_mutator",
            "status": "pass",
            "candidate_yaml": str(Path(args.output_yaml).resolve()),
            "operation": args.operation,
            "reason": args.reason,
        }
        exit_code = 0
    except Exception as exc:
        result = {"tool": "factor_mutator", "status": "fail", "errors": [str(exc)]}
        exit_code = 2

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_json:
        Path(args.result_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
