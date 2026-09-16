"""Static validation for generated factor definitions."""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    """Serializable result of static factor checks."""

    status: str
    checks: dict[str, str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": "factor_checker",
            "status": self.status,
            "code_check": "pass" if self.status == "pass" else "fail",
            "checks": self.checks,
            "errors": self.errors,
        }


def _find_factor_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return top-level functions that could be factor entry points."""

    return [
        node
        for node in getattr(tree, "body", [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


def _has_return_expression(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check that every non-trivial execution path has a returned expression."""

    returns = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Return)
    ]
    return bool(returns) and all(node.value is not None for node in returns)


def _contains_obvious_lookahead(source: str, tree: ast.AST) -> list[str]:
    """Detect simple, unambiguous future-data patterns without financial inference."""

    errors: list[str] = []
    if re.search(r"\.shift\s*\(\s*-", source):
        errors.append("Negative shift is obvious lookahead and is forbidden.")

    future_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id.lower() in {"future", "future_return"}
    }
    if future_names:
        errors.append(f"Use of likely future variables is forbidden: {sorted(future_names)}.")
    return errors


def check_factor_code(factor: dict[str, Any]) -> CheckResult:
    """Run lightweight syntax, contract, and lookahead checks."""

    checks = {
        "syntax": "fail",
        "factor_function": "fail",
        "return_shape": "fail",
        "no_obvious_lookahead": "fail",
    }
    errors: list[str] = []
    source = factor.get("python_code")
    expected_name = factor.get("name")

    if not isinstance(source, str) or not source.strip():
        return CheckResult("fail", checks, ["python_code must be a non-empty string."])
    if not isinstance(expected_name, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", expected_name
    ):
        errors.append("name must be a Python-safe lowercase identifier.")

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        errors.append(f"Python syntax error: line {exc.lineno}: {exc.msg}")
        return CheckResult("fail", checks, errors)

    checks["syntax"] = "pass"
    functions = _find_factor_functions(tree)
    candidates = [item for item in functions if item.name == expected_name]
    if not candidates:
        errors.append(f"Top-level factor function {expected_name!r} was not found.")
        errors.extend(_contains_obvious_lookahead(source, tree))
        checks["no_obvious_lookahead"] = "pass" if not errors else "fail"
        return CheckResult("fail", checks, errors)

    checks["factor_function"] = "pass"
    function = candidates[0]
    args = function.args
    positional = args.posonlyargs + args.args
    if (
        isinstance(function, ast.AsyncFunctionDef)
        or len(positional) != 1
        or args.vararg is not None
        or args.kwarg is not None
        or any(arg.arg != "df" for arg in positional)
    ):
        errors.append("Factor function must be synchronous and accept exactly one argument named df.")
    if not _has_return_expression(function):
        errors.append("Factor function must return a value on every normal path.")
    else:
        checks["return_shape"] = "pass"

    lookahead_errors = _contains_obvious_lookahead(source, tree)
    errors.extend(lookahead_errors)
    checks["no_obvious_lookahead"] = "pass" if not lookahead_errors else "fail"
    return CheckResult("pass" if not errors else "fail", checks, errors)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-json", required=True, help="Generated factor JSON file.")
    parser.add_argument("--output-json", help="Optional JSON result path.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    factor = json.loads(Path(args.factor_json).read_text(encoding="utf-8"))
    result = check_factor_code(factor)
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result.status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

