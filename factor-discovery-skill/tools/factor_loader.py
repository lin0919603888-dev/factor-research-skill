"""Scan a factor library directory and load every YAML factor document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factor_common import read_yaml, validate_factor_document


def load_factor_library(library_dir: str | Path) -> dict[str, Any]:
    """Load all ``*.yaml`` and ``*.yml`` files under a directory.

    The scan is recursive because a real library may organize factors into
    category subdirectories. Invalid files are reported without preventing
    the caller from seeing valid factors.
    """

    root = Path(library_dir)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Factor library directory does not exist: {root}")

    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )
    factors: list[dict[str, Any]] = []
    invalid_files: list[dict[str, str]] = []
    for path in paths:
        try:
            document = read_yaml(path)
            validation = validate_factor_document(document)
            if not validation.passed:
                invalid_files.append({
                    "path": str(path),
                    "errors": "; ".join(validation.errors),
                })
                continue
            enriched = dict(document)
            metadata = dict(enriched.get("metadata") or {})
            metadata.setdefault("source", "library")
            metadata.setdefault("generation", 1)
            metadata["library_path"] = str(path.resolve())
            enriched["metadata"] = metadata
            factors.append(enriched)
        except Exception as exc:
            invalid_files.append({"path": str(path), "errors": str(exc)})

    categories: dict[str, int] = {}
    formula_types: dict[str, int] = {}
    for factor in factors:
        categories[factor["category"]] = categories.get(factor["category"], 0) + 1
        formula_types[factor["formula_type"]] = formula_types.get(factor["formula_type"], 0) + 1

    return {
        "library": str(root.resolve()),
        "file_count": len(paths),
        "loaded_count": len(factors),
        "categories": categories,
        "formula_types": formula_types,
        "factors": factors,
        "invalid_files": invalid_files,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", default="factor_library", help="Factor YAML directory.")
    parser.add_argument("--output-json", help="Optional load summary JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        summary = load_factor_library(args.library)
        exit_code = 0
    except Exception as exc:
        summary = {"status": "fail", "errors": [str(exc)]}
        exit_code = 2

    summary["tool"] = "factor_loader"
    summary["status"] = "pass" if exit_code == 0 and not summary.get("invalid_files") else (
        "fail" if exit_code == 2 else "warn"
    )
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
