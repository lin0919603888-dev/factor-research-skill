"""End-to-end tests for factor loading, evolution, execution, and persistence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Any

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _run_tool(script: Path, arguments: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in {0, 2}:
        raise AssertionError(
            f"Unexpected failure: {completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def _write_research_requirement(path: Path) -> None:
    path.write_text(
        """# Research Goal
Test whether mined price factors have short-term continuation.

# Data Frequency
minute

# Prediction Horizon
1

# Research Direction
Derive robust variations from existing mined price mechanisms.

# Constraints
- Use only supplied minute-bar fields.
- Record every modification reason.

# Evaluation
- min_rank_ic: 0.00
- min_icir: 0.00
- min_ic_observations: 10
""",
        encoding="utf-8",
    )


def _write_factor_library(library: Path) -> None:
    library.mkdir(parents=True, exist_ok=True)
    first = {
        "name": "Mined_close_open_ratio_1",
        "code": "((close / open) * 1.5 + close / 2)",
        "category": "自定义",
        "description": "通过遗传算法挖掘的因子",
        "formula_type": "expression",
    }
    second = {
        "name": "Mined_volume_price_trend_1",
        "code": "((close / average - 1) * volume)",
        "category": "volume_price",
        "description": "Mined volume-adjusted price deviation.",
        "formula_type": "expression",
    }
    (library / "factor_001.yaml").write_text(
        yaml.safe_dump(first, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (library / "factor_002.yaml").write_text(
        yaml.safe_dump(second, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _write_market_csv(path: Path) -> None:
    rng = np.random.default_rng(11)
    dates = pd.date_range("2025-01-02 09:30", periods=60, freq="min")
    close = 100 + np.cumsum(rng.normal(0, 0.08, len(dates)))
    average = close * (1 + rng.normal(0, 0.0005, len(dates)))
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": close + rng.normal(0, 0.02, len(dates)),
            "high": close + np.abs(rng.normal(0.03, 0.01, len(dates))),
            "low": close - np.abs(rng.normal(0.03, 0.01, len(dates))),
            "close": close,
            "volume": np.abs(rng.normal(1000, 150, len(dates))),
            "average": average,
            "barCount": rng.integers(10, 100, len(dates)),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


class FactorDiscoveryTests(unittest.TestCase):
    def test_load_generate_execute_evaluate_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            requirement = workspace / "research_requirement.md"
            library = workspace / "factor_library"
            data = workspace / "data" / "market.csv"
            candidates = workspace / "candidates"
            _write_research_requirement(requirement)
            _write_factor_library(library)
            _write_market_csv(data)

            loaded = _run_tool(
                TOOLS / "factor_loader.py",
                ["--library", str(library), "--output-json", str(workspace / "library.json")],
            )
            self.assertEqual(loaded["status"], "pass")
            self.assertEqual(loaded["loaded_count"], 2)

            generated = _run_tool(
                TOOLS / "factor_generator.py",
                [
                    "--requirement", str(requirement),
                    "--library", str(library),
                    "--strategy", "mutation",
                    "--parent", "Mined_close_open_ratio_1",
                    "--operation", "rolling_zscore",
                    "--reason", "Test a scale-stable variation.",
                    "--output-yaml", str(candidates / "candidate.yaml"),
                ],
            )
            self.assertEqual(generated["status"], "pass")

            validation = _run_tool(
                TOOLS / "factor_executor.py",
                [
                    "--factor-yaml", str(candidates / "candidate.yaml"),
                    "--validate-only",
                    "--result-json", str(candidates / "validation.json"),
                ],
            )
            if validation["status"] != "pass":
                self.fail(json.dumps(validation, ensure_ascii=False))

            execution = _run_tool(
                TOOLS / "factor_executor.py",
                [
                    "--factor-yaml", str(candidates / "candidate.yaml"),
                    "--market-csv", str(data),
                    "--output-csv", str(candidates / "factor_values.csv"),
                    "--result-json", str(candidates / "execution.json"),
                ],
            )
            self.assertEqual(execution["status"], "pass")

            backtest = _run_tool(
                TOOLS / "backtest_runner.py",
                [
                    "--factor-csv", str(candidates / "factor_values.csv"),
                    "--market-csv", str(data),
                    "--horizon", "1",
                    "--output-json", str(candidates / "backtest.json"),
                ],
            )
            self.assertEqual(backtest["status"], "pass")
            self.assertEqual(backtest["backtest"]["method"], "rolling_time_series")

            evaluation = _run_tool(
                TOOLS / "evaluator.py",
                [
                    "--metrics-json", str(candidates / "backtest.json"),
                    "--requirement", str(requirement),
                    "--output-json", str(candidates / "evaluation.json"),
                ],
            )
            self.assertIn(evaluation["gate"], {"pass", "reject"})

            saved = _run_tool(
                TOOLS / "factor_saver.py",
                [
                    "--factor-yaml", str(candidates / "candidate.yaml"),
                    "--library", str(library),
                    "--metrics-json", str(candidates / "backtest.json"),
                    "--evaluation-json", str(candidates / "evaluation.json"),
                    "--output-json", str(candidates / "save.json"),
                ],
            )
            self.assertEqual(saved["status"], "pass")
            saved_path = Path(saved["saved_yaml"])
            self.assertTrue(saved_path.exists())
            self.assertFalse(saved["overwritten"])

            second_generated = _run_tool(
                TOOLS / "factor_generator.py",
                [
                    "--requirement", str(requirement),
                    "--library", str(library),
                    "--strategy", "mutation",
                    "--parent", "Mined_volume_price_trend_1",
                    "--operation", "rolling_rank",
                    "--reason", "Test a rank-based variation.",
                    "--output-yaml", str(candidates / "candidate_two.yaml"),
                ],
            )
            self.assertEqual(second_generated["status"], "pass")

            # Keep YAML-loading deterministic and verify no library files are overwritten.
            file_count_before = len(list(library.glob("*.yaml")))
            saved_again = _run_tool(
                TOOLS / "factor_saver.py",
                [
                    "--factor-yaml", str(candidates / "candidate_two.yaml"),
                    "--library", str(library),
                ],
            )
            self.assertEqual(saved_again["status"], "pass")
            self.assertNotEqual(Path(saved_again["saved_yaml"]), saved_path)
            self.assertEqual(len(list(library.glob("*.yaml"))), file_count_before + 1)

    def test_crossover_records_two_parents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            requirement = workspace / "research_requirement.md"
            library = workspace / "factor_library"
            _write_research_requirement(requirement)
            _write_factor_library(library)
            generated = _run_tool(
                TOOLS / "factor_generator.py",
                [
                    "--requirement", str(requirement),
                    "--library", str(library),
                    "--strategy", "crossover",
                    "--parent", "Mined_close_open_ratio_1",
                    "--parent", "Mined_volume_price_trend_1",
                    "--reason", "Test whether the two mined mechanisms agree.",
                    "--output-yaml", str(workspace / "crossover.yaml"),
                ],
            )
            self.assertEqual(generated["status"], "pass")
            document = yaml.safe_load(
                (workspace / "crossover.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(document["metadata"]["source"], "crossover")
            self.assertEqual(len(document["metadata"]["lineage"]["parents"]), 2)

    def test_initial_candidate_can_be_saved_without_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            requirement = workspace / "research_requirement.md"
            library = workspace / "factor_library"
            code_file = workspace / "initial_factor.txt"
            _write_research_requirement(requirement)
            _write_factor_library(library)
            code_file.write_text("close / average", encoding="utf-8")

            generated = _run_tool(
                TOOLS / "factor_generator.py",
                [
                    "--requirement", str(requirement),
                    "--library", str(library),
                    "--strategy", "initial",
                    "--parent", "Initial_price_deviation",
                    "--code-file", str(code_file),
                    "--reason", "Introduce a simple price-deviation baseline.",
                    "--output-yaml", str(workspace / "initial.yaml"),
                ],
            )
            self.assertEqual(generated["status"], "pass")

            saved = _run_tool(
                TOOLS / "factor_saver.py",
                [
                    "--factor-yaml", str(workspace / "initial.yaml"),
                    "--library", str(library),
                ],
            )
            self.assertEqual(saved["status"], "pass")


if __name__ == "__main__":
    unittest.main()
