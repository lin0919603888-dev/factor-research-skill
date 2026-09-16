"""Configurable pass/reject decision for program-calculated factor metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_RULES: dict[str, Any] = {
    "min_rank_ic_mean": 0.02,
    "min_icir": 0.30,
    "min_ic_observations": 20,
    "require_no_missing_metrics": True,
}


def _check(metric: float | None, threshold: float, comparison: str) -> bool:
    if metric is None:
        return False
    if comparison == "gte":
        return metric >= threshold
    if comparison == "abs_gte":
        return abs(metric) >= threshold
    raise ValueError(f"Unknown comparison: {comparison}")


def evaluate_gate(metrics: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate metrics against explicit thresholds and return an auditable result."""

    active_rules = {**DEFAULT_RULES, **(rules or {})}
    backtest = metrics.get("backtest", metrics)
    rank_ic = backtest.get("RankIC")
    icir = backtest.get("ICIR")
    observations = backtest.get("ic_observations")

    checks = {
        "RankIC_mean": {
            "value": rank_ic,
            "threshold": active_rules["min_rank_ic_mean"],
            "passed": _check(rank_ic, float(active_rules["min_rank_ic_mean"]), "gte"),
        },
        "ICIR": {
            "value": icir,
            "threshold": active_rules["min_icir"],
            "passed": _check(icir, float(active_rules["min_icir"]), "gte"),
        },
        "IC_observations": {
            "value": observations,
            "threshold": active_rules["min_ic_observations"],
            "passed": _check(
                float(observations) if observations is not None else None,
                float(active_rules["min_ic_observations"]),
                "gte",
            ),
        },
    }
    if active_rules.get("require_no_missing_metrics", True):
        missing = [name for name in ("RankIC", "ICIR") if backtest.get(name) is None]
        checks["no_missing_metrics"] = {
            "value": missing,
            "passed": not missing,
        }

    gate = "pass" if all(item["passed"] for item in checks.values()) else "reject"
    return {
        "tool": "gate_checker",
        "gate": gate,
        "checks": checks,
        "rules": active_rules,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-json", required=True, help="backtest_runner JSON output.")
    parser.add_argument("--config", help="Optional gate-rule JSON file.")
    parser.add_argument("--output-json", help="Optional gate result JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    metrics = json.loads(Path(args.metrics_json).read_text(encoding="utf-8"))
    rules = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else None
    result = evaluate_gate(metrics, rules)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["gate"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

