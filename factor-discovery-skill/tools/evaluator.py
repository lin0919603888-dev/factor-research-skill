"""Evaluate program-produced metrics against rules from the research requirement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_common import parse_research_requirement  # noqa: E402


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_metrics(metrics: dict[str, Any], requirement: dict[str, Any]) -> dict[str, Any]:
    """Apply generic evaluation thresholds declared by the current experiment."""

    rules = dict(requirement.get("evaluation") or {})
    backtest = metrics.get("backtest", metrics)
    rank_ic = _number(backtest.get("RankIC"))
    icir = _number(backtest.get("ICIR"))
    observations = _number(backtest.get("ic_observations"))

    min_rank_ic = _number(rules.get("min_rank_ic", 0.0))
    min_icir = _number(rules.get("min_icir", 0.0))
    min_observations = _number(rules.get("min_ic_observations", 2))
    if min_rank_ic is None or min_icir is None or min_observations is None:
        raise ValueError(
            "Evaluation rules min_rank_ic, min_icir, and min_ic_observations must be numeric."
        )

    checks = {
        "RankIC": {
            "value": rank_ic,
            "threshold": min_rank_ic,
            "passed": rank_ic is not None and rank_ic >= min_rank_ic,
        },
        "ICIR": {
            "value": icir,
            "threshold": min_icir,
            "passed": icir is not None and icir >= min_icir,
        },
        "IC_observations": {
            "value": observations,
            "threshold": min_observations,
            "passed": observations is not None and observations >= min_observations,
        },
    }
    gate = "pass" if all(check["passed"] for check in checks.values()) else "reject"
    return {
        "tool": "evaluator",
        "status": gate,
        "gate": gate,
        "checks": checks,
        "rules": {
            "min_rank_ic": min_rank_ic,
            "min_icir": min_icir,
            "min_ic_observations": min_observations,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-json", required=True, help="backtest_runner output JSON.")
    parser.add_argument("--requirement", required=True, help="research_requirement.md or YAML.")
    parser.add_argument("--output-json", required=True, help="Evaluation result JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        metrics = json.loads(Path(args.metrics_json).read_text(encoding="utf-8"))
        requirement = parse_research_requirement(args.requirement)
        result = evaluate_metrics(metrics, requirement)
        exit_code = 0 if result["gate"] == "pass" else 2
    except Exception as exc:
        result = {"tool": "evaluator", "status": "fail", "gate": "reject", "errors": [str(exc)]}
        exit_code = 2
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
