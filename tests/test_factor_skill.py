"""End-to-end smoke tests for the minimal factor research skill."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _run_python(script: Path, arguments: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(script), *arguments]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in {0, 2}:
        raise AssertionError(
            "Unexpected failure: "
            f"{completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def _write_market_csv(path: Path) -> None:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2025-01-02 09:30", periods=80, freq="min")
    close = 100 + np.cumsum(rng.normal(0, 0.08, size=len(dates)))
    average = close * (1 + rng.normal(0, 0.0005, size=len(dates)))
    volume = np.abs(rng.normal(1_000, 150, size=len(dates)))
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": close + rng.normal(0, 0.02, size=len(dates)),
            "high": close + np.abs(rng.normal(0.03, 0.01, size=len(dates))),
            "low": close - np.abs(rng.normal(0.03, 0.01, size=len(dates))),
            "close": close,
            "volume": volume,
            "average": average,
            "barCount": rng.integers(10, 100, size=len(dates)),
        }
    )
    frame.to_csv(path, index=False)


class FactorSkillTests(unittest.TestCase):
    def test_checker_rejects_negative_shift(self) -> None:
        factor = {
            "name": "future_factor",
            "python_code": (
                "import pandas as pd\n\n"
                "def future_factor(df: pd.DataFrame) -> pd.Series:\n"
                "    factor = df['close'].shift(-1)\n"
                "    factor.name = 'future_factor'\n"
                "    return factor\n"
            ),
        }
        path = ROOT / ".tmp_future_factor.json"
        path.write_text(json.dumps(factor), encoding="utf-8")
        try:
            result = _run_python(
                TOOLS / "factor_checker.py",
                ["--factor-json", str(path)],
            )
        finally:
            path.unlink()
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"]["no_obvious_lookahead"], "fail")

    def test_end_to_end_tool_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            market_csv = tmp_path / "market.csv"
            factor_csv = tmp_path / "factor_values.csv"
            check_json = tmp_path / "check.json"
            execution_json = tmp_path / "execution.json"
            backtest_json = tmp_path / "backtest.json"
            gate_json = tmp_path / "gate.json"
            _write_market_csv(market_csv)

            check_result = _run_python(
                TOOLS / "factor_checker.py",
                [
                    "--factor-json", str(ROOT / "examples" / "factor_example.json"),
                    "--output-json", str(check_json),
                ],
            )
            self.assertEqual(check_result["status"], "pass")

            execution_result = _run_python(
                TOOLS / "factor_executor.py",
                [
                    "--factor-json", str(ROOT / "examples" / "factor_example.json"),
                    "--market-csv", str(market_csv),
                    "--output-csv", str(factor_csv),
                    "--result-json", str(execution_json),
                ],
            )
            self.assertEqual(execution_result["status"], "pass")
            self.assertTrue(factor_csv.exists())

            backtest_result = _run_python(
                TOOLS / "backtest_runner.py",
                [
                    "--factor-csv", str(factor_csv),
                    "--market-csv", str(market_csv),
                    "--horizon", "1",
                    "--output-json", str(backtest_json),
                ],
            )
            if backtest_result["status"] != "pass":
                self.fail(json.dumps(backtest_result, ensure_ascii=False))
            self.assertEqual(
                backtest_result["backtest"]["method"], "rolling_time_series"
            )
            self.assertIsNone(backtest_result["return_performance"])

            gate_result = _run_python(
                TOOLS / "gate_checker.py",
                [
                    "--metrics-json", str(backtest_json),
                    "--output-json", str(gate_json),
                ],
            )
            self.assertIn(gate_result["gate"], {"pass", "reject"})
            self.assertTrue(gate_json.exists())

    def test_metric_calculator_cross_sectional_mode(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "metric_calculator", TOOLS / "metric_calculator.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        frame = pd.DataFrame(
            {
                "date": ["d1", "d1", "d1", "d2", "d2", "d2"],
                "factor": [1, 2, 3, 3, 2, 1],
                "forward_return": [0.01, 0.02, 0.03, 0.03, 0.02, 0.01],
            }
        )
        metrics = module.calculate_metrics(frame)
        self.assertEqual(metrics["method"], "cross_sectional")
        self.assertAlmostEqual(metrics["IC"], 1.0)
        self.assertAlmostEqual(metrics["RankIC"], 1.0)


if __name__ == "__main__":
    unittest.main()
