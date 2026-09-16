"""Validate and execute YAML-defined minute-bar factors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_common import (  # noqa: E402
    execute_factor_document,
    load_market_data,
    read_yaml,
    validate_factor_document,
)


def validate_only(document: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic structural and source-level validation."""

    result = validate_factor_document(document)
    return {
        "tool": "factor_executor",
        "mode": "validate_only",
        "status": result.status,
        "validation": result.status,
        "errors": result.errors,
    }


def execute_yaml(
    factor_yaml: str | Path,
    market_csv: str | Path,
    output_csv: str | Path,
) -> dict[str, Any]:
    """Validate a factor YAML, execute it, and persist its Series as CSV."""

    document = read_yaml(factor_yaml)
    validation = validate_factor_document(document)
    if not validation.passed:
        return {
            "tool": "factor_executor",
            "mode": "execute",
            "status": "fail",
            "validation": "fail",
            "errors": validation.errors,
        }
    market = load_market_data(market_csv)
    values = execute_factor_document(document, market)
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    values.to_csv(output, index=True, index_label="date", header=True)
    return {
        "tool": "factor_executor",
        "mode": "execute",
        "status": "pass",
        "validation": "pass",
        "factor_name": document["name"],
        "output_csv": str(output.resolve()),
        "rows": int(len(values)),
        "finite_rows": int(values.notna().sum()),
        "errors": [],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-yaml", required=True, help="Factor or candidate YAML.")
    parser.add_argument("--market-csv", help="Minute CSV; required unless --validate-only is set.")
    parser.add_argument("--output-csv", help="Factor CSV; required unless --validate-only is set.")
    parser.add_argument("--validate-only", action="store_true", help="Validate without execution.")
    parser.add_argument("--result-json", help="Optional execution result JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.validate_only:
            if args.market_csv or args.output_csv:
                raise ValueError("--validate-only cannot be combined with market/output paths.")
            result = validate_only(read_yaml(args.factor_yaml))
        else:
            if not args.market_csv or not args.output_csv:
                raise ValueError("Execution requires --market-csv and --output-csv.")
            result = execute_yaml(args.factor_yaml, args.market_csv, args.output_csv)
        exit_code = 0 if result["status"] == "pass" else 2
    except Exception as exc:
        result = {
            "tool": "factor_executor",
            "status": "fail",
            "validation": "not_run",
            "errors": [str(exc)],
        }
        exit_code = 2

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_json:
        Path(args.result_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
