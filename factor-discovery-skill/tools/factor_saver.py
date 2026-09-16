"""Persist evaluated candidate factors without overwriting library history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_common import read_yaml, utc_now, validate_factor_document, write_yaml  # noqa: E402


def _unique_path(directory: Path, name: str) -> Path:
    """Return an unused YAML path derived from the factor name."""

    slug = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "candidate_factor"
    base = directory / f"{slug}.yaml"
    if not base.exists():
        return base
    sequence = 2
    while True:
        candidate = directory / f"{slug}_{sequence:03d}.yaml"
        if not candidate.exists():
            return candidate
        sequence += 1


def save_factor(
    candidate: dict[str, Any],
    library_dir: str | Path,
    *,
    backtest: dict[str, Any] | None = None,
    evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a validated candidate under a unique path and attach evaluation."""

    validation = validate_factor_document(candidate, candidate=True)
    if not validation.passed:
        raise ValueError("Candidate validation failed: " + "; ".join(validation.errors))

    directory = Path(library_dir)
    directory.mkdir(parents=True, exist_ok=True)
    metadata = dict(candidate.get("metadata") or {})
    evaluation_record: dict[str, Any] = {}
    if backtest is not None:
        evaluation_record["metrics"] = backtest.get("backtest", backtest)
    if evaluation is not None:
        evaluation_record["gate"] = evaluation.get("gate")
        evaluation_record["checks"] = evaluation.get("checks")
        evaluation_record["rules"] = evaluation.get("rules")
    metadata["evaluation"] = evaluation_record
    metadata["saved_at"] = utc_now()

    final_candidate = dict(candidate)
    final_candidate["metadata"] = metadata
    target = _unique_path(directory, final_candidate["name"])
    write_yaml(final_candidate, target)
    if target.stat().st_size <= 0:
        raise IOError(f"Saved factor is empty: {target}")

    return {
        "tool": "factor_saver",
        "status": "pass",
        "saved_yaml": str(target.resolve()),
        "factor_name": final_candidate["name"],
        "overwritten": False,
        "generation": final_candidate["metadata"]["generation"],
        "evaluation_recorded": bool(evaluation_record),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-yaml", required=True, help="Candidate YAML to archive.")
    parser.add_argument("--library", default="factor_library", help="Destination factor library.")
    parser.add_argument("--metrics-json", help="Optional backtest_runner JSON.")
    parser.add_argument("--evaluation-json", help="Optional evaluator JSON.")
    parser.add_argument("--output-json", help="Optional saver result JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        candidate = read_yaml(args.factor_yaml)
        backtest = (
            json.loads(Path(args.metrics_json).read_text(encoding="utf-8"))
            if args.metrics_json else None
        )
        evaluation = (
            json.loads(Path(args.evaluation_json).read_text(encoding="utf-8"))
            if args.evaluation_json else None
        )
        result = save_factor(
            candidate,
            args.library,
            backtest=backtest,
            evaluation=evaluation,
        )
        exit_code = 0
    except Exception as exc:
        result = {"tool": "factor_saver", "status": "fail", "errors": [str(exc)]}
        exit_code = 2

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
