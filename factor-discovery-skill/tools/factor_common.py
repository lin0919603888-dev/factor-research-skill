"""Shared parsing, validation, and execution helpers for factor discovery."""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd
import yaml


FACTOR_COLUMNS = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "average",
    "barCount",
}


class FactorDocumentError(ValueError):
    """Raised when a factor or research requirement document is invalid."""


class FactorExecutionError(RuntimeError):
    """Raised when a factor cannot be validated or executed."""


@dataclass(frozen=True)
class ValidationResult:
    """Result returned by deterministic document and code checks."""

    status: str
    errors: list[str]

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def utc_now() -> str:
    """Return a stable UTC timestamp for provenance records."""

    return datetime.now(timezone.utc).isoformat()


def read_yaml(path: str | Path) -> dict[str, Any]:
    """Read one YAML file and require an object at the top level."""

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise FactorDocumentError(f"YAML document must be an object: {path}")
    return document


def write_yaml(document: dict[str, Any], path: str | Path) -> None:
    """Write a YAML object atomically enough for a local research workflow."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    temporary.replace(target)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return slug or "factor"


def validate_factor_document(
    document: dict[str, Any],
    *,
    candidate: bool = False,
) -> ValidationResult:
    """Validate required fields, formula type, and obvious lookahead patterns."""

    errors: list[str] = []
    for field in ("name", "code", "formula_type", "category", "description"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing non-empty string field: {field}.")

    if errors:
        return ValidationResult("fail", errors)

    name = document["name"]
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        errors.append("name must be a Python-safe identifier.")

    formula_type = document["formula_type"]
    if formula_type not in {"expression", "python"}:
        errors.append("formula_type must be 'expression' or 'python'.")
    elif formula_type == "expression":
        errors.extend(validate_expression(document["code"]))
    else:
        errors.extend(validate_python_factor(document["code"], expected_name=name))

    if candidate:
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            errors.append("Candidate metadata must be an object.")
        else:
            for field in ("source", "generation", "lineage"):
                if field not in metadata:
                    errors.append(f"Candidate metadata is missing: {field}.")
            if "source" in metadata and metadata["source"] not in {
                "initial",
                "mutation",
                "crossover",
                "refinement",
            }:
                errors.append("metadata.source has an unsupported evolution strategy.")
            if "reason" in metadata and not str(metadata["reason"]).strip():
                errors.append("metadata.reason must not be empty.")
            lineage = metadata.get("lineage")
            if not isinstance(lineage, dict) or not isinstance(lineage.get("parents"), list):
                errors.append("metadata.lineage.parents must be a list.")
            else:
                parent_count = len(lineage["parents"])
                source = metadata.get("source")
                if source in {"mutation", "refinement"} and parent_count != 1:
                    errors.append(f"{source} lineage must contain exactly one parent.")
                if source == "crossover" and parent_count != 2:
                    errors.append("crossover lineage must contain exactly two parents.")
                if source == "initial" and parent_count != 0:
                    errors.append("initial lineage must contain no parent factors.")

    return ValidationResult("pass" if not errors else "fail", errors)


def validate_expression(expression: str) -> list[str]:
    """Allow arithmetic expressions while rejecting calls and attribute access."""

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return [f"Invalid expression syntax on line {exc.lineno}: {exc.msg}"]

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            return [
                f"Unsupported expression node: {type(node).__name__}. "
                "Expression factors may use column names and arithmetic only."
            ]
    return []


def validate_python_factor(source: str, expected_name: str) -> list[str]:
    """Validate Python factor shape and reject obvious lookahead."""

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return [f"Invalid Python syntax on line {exc.lineno}: {exc.msg}"]

    if re.search(r"\.shift\s*\(\s*-", source):
        return ["Negative shift is obvious lookahead and is forbidden."]

    functions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == expected_name
    ]
    if not functions:
        return [f"Top-level factor function {expected_name!r} was not found."]

    function = functions[0]
    args = function.args
    positional = args.posonlyargs + args.args
    if (
        isinstance(function, ast.AsyncFunctionDef)
        or len(positional) != 1
        or positional[0].arg != "df"
        or args.vararg is not None
        or args.kwarg is not None
    ):
        return ["Python factor must accept exactly one argument named df."]

    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    if not returns or any(node.value is None for node in returns):
        return ["Python factor must return a value on every normal path."]
    return []


def parse_research_requirement(path: str | Path) -> dict[str, Any]:
    """Parse either structured YAML or a simple Markdown research requirement."""

    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise FactorDocumentError("Research requirement is empty.")

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        parsed = None

    if isinstance(parsed, dict):
        requirement = parsed
    else:
        requirement = _parse_requirement_markdown(text)

    normalized = {_snake_case(key): value for key, value in requirement.items()}
    missing = [
        field for field in (
            "research_goal",
            "data_frequency",
            "prediction_horizon",
            "research_direction",
            "constraints",
            "evaluation",
        )
        if field not in normalized
    ]
    if missing:
        raise FactorDocumentError(f"Research requirement is missing: {missing}.")
    if not isinstance(normalized["evaluation"], dict):
        normalized["evaluation"] = {}
    if not isinstance(normalized["constraints"], list):
        normalized["constraints"] = [str(normalized["constraints"])]
    return normalized


def _parse_requirement_markdown(text: str) -> dict[str, Any]:
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for raw_line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", raw_line)
        if heading:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = heading.group(1)
            lines = []
        elif current is not None:
            lines.append(raw_line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()

    if not sections:
        raise FactorDocumentError(
            "Research requirement must use YAML keys or Markdown sections."
        )

    parsed: dict[str, Any] = {}
    for title, body in sections.items():
        if _snake_case(title) == "research_requirement":
            continue
        structured = _parse_section(body)
        parsed[title] = structured
    return parsed


def _parse_section(body: str) -> Any:
    nonempty = [line.strip() for line in body.splitlines() if line.strip()]
    if not nonempty:
        return ""
    bullet_lines = [line.lstrip("-* ").strip() for line in nonempty if re.match(r"^[-*]\s+", line.strip())]
    if bullet_lines:
        pair_lines = []
        for line in bullet_lines:
            if ":" in line:
                key, value = line.split(":", 1)
                pair_lines.append((key.strip(), value.strip()))
            else:
                return bullet_lines
        return {key: value for key, value in pair_lines}

    if all(":" in line for line in nonempty):
        return dict(line.split(":", 1) for line in nonempty)
    return " ".join(nonempty)


def _snake_case(value: str) -> str:
    value = value.strip().replace("-", " ").replace("_", " ")
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return value.lower()
    return words[0].lower() + "".join("_" + word.lower() for word in words[1:])


def load_market_data(market_csv: str | Path) -> pd.DataFrame:
    """Load the documented minute CSV format and normalize its datetime index."""

    frame = pd.read_csv(market_csv)
    missing = sorted(FACTOR_COLUMNS.difference(frame.columns))
    if missing:
        raise FactorExecutionError(f"Market CSV is missing documented fields: {missing}.")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    return frame.set_index("date", drop=True).sort_index()


def execute_factor_document(
    document: dict[str, Any],
    market_data: pd.DataFrame,
) -> pd.Series:
    """Execute an expression or Python factor and enforce a numeric Series result."""

    validation = validate_factor_document(document)
    if not validation.passed:
        raise FactorExecutionError("; ".join(validation.errors))

    name = document["name"]
    if document["formula_type"] == "expression":
        try:
            result = eval(  # noqa: S307 - AST-validated arithmetic only.
                compile(document["code"], "<factor-expression>", "eval"),
                {"__builtins__": {}},
                {column: market_data[column] for column in market_data.columns},
            )
        except Exception as exc:
            raise FactorExecutionError(f"Expression factor execution failed: {exc}") from exc
    else:
        function = _load_python_function(document["code"], name)
        try:
            result = function(market_data.copy())
        except Exception as exc:
            raise FactorExecutionError(f"Python factor execution failed: {exc}") from exc

    if not isinstance(result, pd.Series):
        raise FactorExecutionError(
            f"Factor returned {type(result).__name__}; expected pandas.Series."
        )
    if len(result) != len(market_data):
        raise FactorExecutionError(
            f"Factor length {len(result)} does not match input length {len(market_data)}."
        )
    numeric = pd.to_numeric(result, errors="coerce").astype(float)
    numeric.name = name
    if not numeric.index.equals(market_data.index):
        numeric.index = market_data.index
    return numeric


def _load_python_function(source: str, function_name: str):
    """Import generated Python source from an isolated temporary module path."""

    with tempfile.TemporaryDirectory(prefix="factor_discovery_") as temp_dir:
        module_path = Path(temp_dir) / "candidate_factor.py"
        module_path.write_text(source, encoding="utf-8")
        spec = spec_from_file_location("candidate_factor_module", module_path)
        if spec is None or spec.loader is None:
            raise FactorExecutionError("Could not create a Python module specification.")
        module: ModuleType = module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        function = getattr(module, function_name, None)
        if not callable(function):
            raise FactorExecutionError(f"Function {function_name!r} is not callable.")
        return function
