"""Combine exactly two recorded parent factors into one candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_common import read_yaml, validate_factor_document, write_yaml  # noqa: E402


def _parent_binding(parent: dict[str, Any], index: int) -> tuple[str, str]:
    """Return source preamble and assignment for a parent signal."""

    alias = f"parent_{index}"
    if parent["formula_type"] == "expression":
        preamble = ""
        assignment = f"{alias} = df.eval(r'''({parent['code']})''')"
        return preamble, assignment
    preamble = parent["code"] + "\n\n"
    assignment = f"{alias} = {parent['name']}(df)"
    return preamble, assignment


def crossover_factors(
    first_parent: dict[str, Any],
    first_path: str | Path,
    second_parent: dict[str, Any],
    second_path: str | Path,
    *,
    weights: tuple[float, float] = (1.0, 1.0),
    window: int = 20,
    reason: str = (
        "Combine complementary parent signals after rolling z-score normalization."
    ),
) -> dict[str, Any]:
    """Create a weighted, normalized crossover with complete lineage."""

    if len(weights) != 2 or weights[0] <= 0 or weights[1] <= 0:
        raise ValueError("Exactly two positive crossover weights are required.")
    if window < 2:
        raise ValueError("window must be at least 2.")
    if not reason.strip():
        raise ValueError("A non-empty crossover reason is required.")

    parents = [first_parent, second_parent]
    paths = [first_path, second_path]
    for index, parent in enumerate(parents, start=1):
        validation = validate_factor_document(parent)
        if not validation.passed:
            raise ValueError(
                f"Parent {index} is invalid: {'; '.join(validation.errors)}"
            )

    preambles: list[str] = []
    assignments: list[str] = []
    for index, (parent, path) in enumerate(zip(parents, paths), start=1):
        preamble, assignment = _parent_binding(parent, index)
        preambles.append(preamble)
        assignments.append(f"    {assignment}")

    first_metadata = dict(first_parent.get("metadata") or {})
    second_metadata = dict(second_parent.get("metadata") or {})
    generation = max(int(first_metadata.get("generation", 1)), int(second_metadata.get("generation", 1))) + 1
    name_base = f"{first_parent['name']}__x__{second_parent['name']}"
    digest = hashlib.sha1(name_base.encode("utf-8")).hexdigest()[:8]  # noqa: S324 - stable local naming only.
    candidate_name = f"{name_base}_{digest}"
    code = (
        "import pandas as pd\n\n\n"
        + "\n".join(preambles)
        + "\ndef "
        + candidate_name
        + "(df: pd.DataFrame) -> pd.Series:\n"
        + "\n".join(assignments)
        + "\n"
        f"    normalized_1 = parent_1.rolling(window={window}, min_periods=2).mean()\n"
        f"    scale_1 = parent_1.rolling(window={window}, min_periods=2).std().replace(0, float('nan'))\n"
        f"    normalized_2 = parent_2.rolling(window={window}, min_periods=2).mean()\n"
        f"    scale_2 = parent_2.rolling(window={window}, min_periods=2).std().replace(0, float('nan'))\n"
        "    standardized_1 = (parent_1 - normalized_1) / scale_1\n"
        "    standardized_2 = (parent_2 - normalized_2) / scale_2\n"
        f"    factor = ({weights[0]!r} * standardized_1 + {weights[1]!r} * standardized_2) / {sum(weights)!r}\n"
        "    factor = factor.replace([float('inf'), -float('inf')], float('nan'))\n"
        f"    factor.name = {candidate_name!r}\n"
        "    return factor.astype(float)\n"
    )

    return {
        "name": candidate_name,
        "code": code,
        "formula_type": "python",
        "category": "crossover",
        "description": (
            f"Weighted rolling z-score crossover of {first_parent['name']} and "
            f"{second_parent['name']}. {reason.strip()}"
        ),
        "metadata": {
            "source": "crossover",
            "generation": generation,
            "lineage": {
                "parents": [
                    {
                        "name": parent["name"],
                        "path": str(Path(path).resolve()),
                        "formula_type": parent["formula_type"],
                    }
                    for parent, path in zip(parents, paths)
                ],
                "operation": "rolling_zscore_weighted_average",
                "reason": reason.strip(),
                "parameters": {
                    "weights": list(weights),
                    "window": window,
                },
            },
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-yaml", action="append", required=True, help="Exactly two parent YAML paths.")
    parser.add_argument("--weights", nargs=2, type=float, default=[1.0, 1.0])
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--reason", required=True, help="Required research reason for crossover.")
    parser.add_argument("--output-yaml", required=True)
    parser.add_argument("--result-json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if len(args.parent_yaml) != 2:
            raise ValueError("Crossover requires exactly two parent YAML files.")
        first = read_yaml(args.parent_yaml[0])
        second = read_yaml(args.parent_yaml[1])
        candidate = crossover_factors(
            first,
            args.parent_yaml[0],
            second,
            args.parent_yaml[1],
            weights=tuple(args.weights),
            window=args.window,
            reason=args.reason,
        )
        write_yaml(candidate, args.output_yaml)
        result = {
            "tool": "factor_crossover",
            "status": "pass",
            "candidate_yaml": str(Path(args.output_yaml).resolve()),
            "parents": [first["name"], second["name"]],
            "reason": args.reason,
        }
        exit_code = 0
    except Exception as exc:
        result = {"tool": "factor_crossover", "status": "fail", "errors": [str(exc)]}
        exit_code = 2

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_json:
        Path(args.result_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
