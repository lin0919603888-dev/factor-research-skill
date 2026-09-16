"""Run the minimal predictive evaluation loop for one factor Series."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metric_calculator import calculate_metrics  # noqa: E402


def _normalize_date(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "date" not in result.columns:
        raise ValueError("Input data must contain a date column.")
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    return result.sort_values(["date"] + (["symbol"] if "symbol" in result.columns else []))


def _build_forward_returns(market: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Construct horizon-bar close-to-close returns from supplied market data."""

    if "close" not in market.columns:
        raise ValueError("Market CSV must contain close to construct forward returns.")
    result = market.copy()
    if "symbol" in result.columns:
        grouped = result.groupby("symbol", sort=False)["close"]
        future_close = grouped.shift(-horizon)
    else:
        future_close = result["close"].shift(-horizon)
    result["forward_return"] = future_close / result["close"] - 1.0
    return result


def _load_factor_csv(path: str | Path) -> pd.DataFrame:
    factor = pd.read_csv(path)
    if factor.shape[1] < 2:
        raise ValueError("Factor CSV must contain date and factor value columns.")
    factor = factor.rename(columns={factor.columns[1]: "factor"})
    return _normalize_date(factor)


def run_backtest(
    factor_csv: str | Path,
    market_csv: str | Path | None = None,
    returns_csv: str | Path | None = None,
    horizon: int = 1,
    rolling_window: int = 20,
) -> dict[str, Any]:
    """Evaluate factor values against either market data or precomputed returns."""

    if (market_csv is None) == (returns_csv is None):
        raise ValueError("Supply exactly one of market_csv or returns_csv.")
    if horizon < 1:
        raise ValueError("horizon must be a positive integer.")

    factor = _load_factor_csv(factor_csv)
    if market_csv is not None:
        market = _normalize_date(pd.read_csv(market_csv))
        keys = ["date"] + (["symbol"] if {"date", "symbol"}.issubset(factor.columns) and "symbol" in market.columns else [])
        aligned = market.merge(factor, on=keys, how="inner", validate="one_to_one")
        evaluated = _build_forward_returns(aligned, horizon)
    else:
        returns = _normalize_date(pd.read_csv(returns_csv))
        if "forward_return" not in returns.columns:
            raise ValueError("Returns CSV must contain forward_return.")
        keys = ["date"] + (["symbol"] if "symbol" in factor.columns and "symbol" in returns.columns else [])
        evaluated = factor.merge(returns, on=keys, how="inner", validate="one_to_one")

    metrics = calculate_metrics(evaluated, rolling_window=rolling_window)
    return {
        "tool": "backtest_runner",
        "status": "pass",
        "backtest": metrics,
        "inputs": {
            "factor_csv": str(Path(factor_csv).resolve()),
            "market_csv": str(Path(market_csv).resolve()) if market_csv else None,
            "returns_csv": str(Path(returns_csv).resolve()) if returns_csv else None,
            "forward_horizon": horizon,
        },
        "return_performance": None,
        "notes": [
            "This minimal runner reports predictive metrics only.",
            "Portfolio return and transaction-cost performance require a real trading simulator.",
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-csv", required=True, help="CSV with date and factor columns.")
    parser.add_argument("--market-csv", help="Market CSV used to construct forward returns.")
    parser.add_argument("--returns-csv", help="CSV with precomputed aligned forward_return.")
    parser.add_argument("--horizon", type=int, default=1, help="Forward-return horizon in bars.")
    parser.add_argument("--rolling-window", type=int, default=20, help="Window for non-cross-sectional fallback.")
    parser.add_argument("--output-json", required=True, help="Metrics output JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = run_backtest(
            factor_csv=args.factor_csv,
            market_csv=args.market_csv,
            returns_csv=args.returns_csv,
            horizon=args.horizon,
            rolling_window=args.rolling_window,
        )
        exit_code = 0
    except Exception as exc:
        result = {
            "tool": "backtest_runner",
            "status": "fail",
            "backtest": {},
            "errors": [str(exc)],
        }
        exit_code = 2
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
