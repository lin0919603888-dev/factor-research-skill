"""Unified candidate generation entry point for all evolution strategies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_common import (  # noqa: E402
    FactorDocumentError,
    parse_research_requirement,
    read_yaml,
    write_yaml,
)
from factor_loader import load_factor_library  # noqa: E402
from factor_mutator import OPERATIONS, mutate_factor  # noqa: E402
from factor_crossover import crossover_factors  # noqa: E402


def _select_parents(
    summary: dict[str, Any],
    parent_names: list[str],
    expected_count: int,
) -> list[tuple[dict[str, Any], Path]]:
    factors = summary["factors"]
    if parent_names:
        if len(parent_names) != expected_count:
            raise ValueError(f"{expected_count} parent(s) must be supplied for this strategy.")
        selected: list[tuple[dict[str, Any], Path]] = []
        for name in parent_names:
            matches = [
                (factor, Path(factor["metadata"]["library_path"]))
                for factor in factors
                if factor["name"] == name or factor["metadata"]["library_path"] == name
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"Parent {name!r} did not match exactly one valid library factor."
                )
            selected.append(matches[0])
        return selected

    if len(factors) == expected_count:
        return [(factor, Path(factor["metadata"]["library_path"])) for factor in factors]
    raise ValueError(
        f"Strategy requires {expected_count} explicit parent(s); the library contains "
        f"{len(factors)} valid factor(s)."
    )


def generate_candidate(
    requirement_path: str | Path,
    library_path: str | Path,
    strategy: str,
    *,
    parent_names: list[str] | None = None,
    operation: str = "rolling_zscore",
    reason: str | None = None,
    window: int = 20,
    weights: tuple[float, float] = (1.0, 1.0),
    code_file: str | Path | None = None,
) -> dict[str, Any]:
    """Generate one candidate while preserving explicit parent provenance."""

    if strategy not in {"initial", "mutation", "crossover", "refinement"}:
        raise ValueError(f"Unsupported evolution strategy: {strategy}.")
    requirement = parse_research_requirement(requirement_path)
    summary = load_factor_library(library_path)

    research_metadata = {
        "research_goal": requirement["research_goal"],
        "research_direction": requirement["research_direction"],
        "data_frequency": requirement["data_frequency"],
        "prediction_horizon": requirement["prediction_horizon"],
    }

    if strategy == "initial":
        if code_file is None:
            raise ValueError("initial strategy requires --code-file for an explicitly designed factor.")
        source = Path(code_file).read_text(encoding="utf-8")
        stripped = source.strip()
        if stripped.startswith(("import ", "from ", "def ")):
            formula_type = "python"
            if len(parent_names or []) != 1:
                raise ValueError("initial strategy requires one synthetic parent name via --parent.")
            name = (parent_names or [])[0]
        else:
            formula_type = "expression"
            if len(parent_names or []) != 1:
                raise ValueError("initial strategy requires one factor name via --parent.")
            name = (parent_names or [])[0]
        candidate = {
            "name": name,
            "code": source,
            "formula_type": formula_type,
            "category": "initial",
            "description": (
                f"Initial factor designed for: {requirement['research_goal']}. "
                + (reason or "No additional design note supplied.")
            ),
            "metadata": {
                "source": "initial",
                "generation": 1,
                "lineage": {
                    "parents": [],
                    "operation": "manual_design",
                    "reason": reason or "Designed from the current research requirement.",
                },
                **research_metadata,
            },
        }
        return candidate

    if strategy == "crossover":
        selected = _select_parents(summary, parent_names or [], 2)
        effective_reason = reason or (
            "Combine the parents to test whether normalized signals agree."
        )
        candidate = crossover_factors(
            selected[0][0],
            selected[0][1],
            selected[1][0],
            selected[1][1],
            weights=weights,
            window=window,
            reason=effective_reason,
        )
    else:
        if operation not in OPERATIONS:
            raise ValueError(f"Unsupported mutation/refinement operation: {operation}.")
        selected = _select_parents(summary, parent_names or [], 1)
        effective_reason = reason or (
            f"Apply {operation} to test a more stable form of the parent signal."
            if strategy == "refinement"
            else f"Apply {operation} to test a variation of the parent mechanism."
        )
        candidate = mutate_factor(
            selected[0][0],
            selected[0][1],
            operation=operation,
            reason=effective_reason,
            window=window,
        )
        if strategy == "refinement":
            candidate["metadata"]["source"] = "refinement"
            old_name = candidate["name"]
            new_name = old_name.replace("_mut_", "_ref_", 1)
            candidate["name"] = new_name
            candidate["code"] = candidate["code"].replace(
                f"def {old_name}(", f"def {new_name}(", 1
            ).replace(f"{old_name!r}", f"{new_name!r}", 1)

    candidate["metadata"].update(research_metadata)
    return candidate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement", required=True, help="research_requirement.md or YAML.")
    parser.add_argument("--library", default="factor_library", help="Factor library directory.")
    parser.add_argument("--strategy", required=True, choices=["initial", "mutation", "crossover", "refinement"])
    parser.add_argument("--parent", action="append", help="Parent name or YAML path; repeat for crossover.")
    parser.add_argument("--operation", default="rolling_zscore")
    parser.add_argument("--reason", help="Explicit research reason.")
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--weight", action="append", type=float, help="Two weights for crossover.")
    parser.add_argument("--code-file", help="Python/expression source for initial strategy.")
    parser.add_argument("--output-yaml", required=True)
    parser.add_argument("--result-json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        weights = tuple(args.weight) if args.weight else (1.0, 1.0)
        candidate = generate_candidate(
            args.requirement,
            args.library,
            args.strategy,
            parent_names=args.parent,
            operation=args.operation,
            reason=args.reason,
            window=args.window,
            weights=weights,
            code_file=args.code_file,
        )
        write_yaml(candidate, args.output_yaml)
        result = {
            "tool": "factor_generator",
            "status": "pass",
            "strategy": args.strategy,
            "candidate_yaml": str(Path(args.output_yaml).resolve()),
            "candidate_name": candidate["name"],
            "parents": candidate["metadata"]["lineage"]["parents"],
        }
        exit_code = 0
    except Exception as exc:
        result = {"tool": "factor_generator", "status": "fail", "errors": [str(exc)]}
        exit_code = 2

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_json:
        Path(args.result_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
