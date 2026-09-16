"""Program-derived predictive evaluation for candidate minute factors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "date" not in result.columns:
        raise ValueError("Input data must contain a date column.")
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    keys = ["date"] + (["symbol"] if "symbol" in result.columns else [])
    return result.sort_values(keys)


def _load_factor_csv(path: str | Path) -> pd.DataFrame:
    factor = pd.read_csv(path)
    if factor.shape[1] < 2:
        raise ValueError("Factor CSV must contain date and factor columns.")
    factor = factor.rename(columns={factor.columns[1]: "factor"})
    return _normalize(factor)


def _forward_returns(market: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if "close" not in market.columns:
        raise ValueError("Market CSV must contain close to construct forward returns.")
    result = market.copy()
    if "symbol" in result.columns:
        future_close = result.groupby("symbol", sort=False)["close"].shift(-horizon)
    else:
        future_close = result["close"].shift(-horizon)
    result["forward_return"] = future_close / result["close"] - 1.0
    return result


def _mean_or_none(values: pd.Series) -> float | None:
    clean = values.dropna()
    return float(clean.mean()) if not clean.empty else None


def _icir_or_none(values: pd.Series) -> float | None:
    clean = values.dropna().astype(float)
    if len(clean) < 2:
        return None
    standard_deviation = float(clean.std(ddof=0))
    return float(clean.mean() / standard_deviation) if standard_deviation > 0 else None


def _cross_sectional_ics(frame: pd.DataFrame, method: str) -> pd.Series:
    values: dict[Any, float] = {}
    for timestamp, group in frame.groupby("date", sort=True, dropna=False):
        if len(group) < 2 or group["factor"].nunique() < 2 or group["forward_return"].nunique() < 2:
            continue
        correlation = group["factor"].corr(group["forward_return"], method=method)
        if pd.notna(correlation):
            values[timestamp] = float(correlation)
    return pd.Series(values, name=f"{method}_ic")


def _rank_correlation(values: np.ndarray) -> float:
    factor_values = values[:, 0]
    return_values = values[:, 1]
    if np.std(factor_values) == 0 or np.std(return_values) == 0:
        return np.nan
    return float(
        pd.Series(factor_values).corr(pd.Series(return_values), method="spearman")
    )


def _rolling_ics(frame: pd.DataFrame, window: int) -> tuple[pd.Series, pd.Series]:
    pearson = frame["factor"].rolling(window, min_periods=window).corr(
        frame["forward_return"]
    )
    pearson.name = "rolling_pearson_ic"
    paired = frame[["factor", "forward_return"]].to_numpy()
    spearman_values = []
    for index in range(1, len(frame) + 1):
        if index < window:
            spearman_values.append(np.nan)
            continue
        sample = paired[index - window:index]
        spearman_values.append(
            _rank_correlation(sample) if not np.isnan(sample).any() else np.nan
        )
    spearman = pd.Series(spearman_values, index=frame.index, name="rolling_spearman_ic")
    return pearson, spearman


def calculate_metrics(observations: pd.DataFrame, rolling_window: int = 20) -> dict[str, Any]:
    """Calculate IC metrics without inventing missing observations."""

    if rolling_window < 2:
        raise ValueError("rolling_window must be at least 2.")
    if not {"factor", "forward_return"}.issubset(observations.columns):
        raise ValueError("Metric input must contain factor and forward_return columns.")

    clean = observations.dropna(subset=["factor", "forward_return"]).copy()
    has_cross_section = (
        "date" in clean.columns
        and len(clean) > 1
        and int(clean.groupby("date", dropna=False).size().max()) > 1
    )
    if has_cross_section:
        pearson = _cross_sectional_ics(clean, "pearson")
        spearman = _cross_sectional_ics(clean, "spearman")
        method = "cross_sectional"
    else:
        clean = clean.drop(columns=["date"], errors="ignore").reset_index(drop=True)
        pearson, spearman = _rolling_ics(clean, rolling_window)
        method = "rolling_time_series"

    return {
        "IC": _mean_or_none(pearson),
        "RankIC": _mean_or_none(spearman),
        "ICIR": _icir_or_none(pearson),
        "RankICIR": _icir_or_none(spearman),
        "total_observations": int(len(observations)),
        "valid_observations": int(len(clean)),
        "ic_observations": int(pearson.notna().sum()),
        "IC_positive_ratio": (
            float((pearson.dropna() > 0).mean()) if pearson.notna().any() else None
        ),
        "method": method,
        "rolling_window": rolling_window if method == "rolling_time_series" else None,
    }


def run_backtest(
    factor_csv: str | Path,
    market_csv: str | Path | None = None,
    returns_csv: str | Path | None = None,
    horizon: int = 1,
    rolling_window: int = 20,
) -> dict[str, Any]:
    """Evaluate a factor against market data or precomputed forward returns."""

    if (market_csv is None) == (returns_csv is None):
        raise ValueError("Supply exactly one of market-csv or returns-csv.")
    if horizon < 1:
        raise ValueError("horizon must be a positive integer.")

    factor = _load_factor_csv(factor_csv)
    if market_csv is not None:
        market = _normalize(pd.read_csv(market_csv))
        keys = ["date"] + (
            ["symbol"]
            if {"date", "symbol"}.issubset(factor.columns) and "symbol" in market.columns
            else []
        )
        aligned = market.merge(factor, on=keys, how="inner", validate="one_to_one")
        evaluated = _forward_returns(aligned, horizon)
    else:
        returns = _normalize(pd.read_csv(returns_csv))
        if "forward_return" not in returns.columns:
            raise ValueError("Returns CSV must contain forward_return.")
        keys = ["date"] + (
            ["symbol"] if "symbol" in factor.columns and "symbol" in returns.columns else []
        )
        evaluated = factor.merge(returns, on=keys, how="inner", validate="one_to_one")

    metrics = calculate_metrics(evaluated, rolling_window)
    return {
        "tool": "backtest_runner",
        "status": "pass",
        "backtest": metrics,
        "inputs": {
            "factor_csv": str(Path(factor_csv).resolve()),
            "market_csv": str(Path(market_csv).resolve()) if market_csv else None,
            "returns_csv": str(Path(returns_csv).resolve()) if returns_csv else None,
            "prediction_horizon": horizon,
        },
        "return_performance": None,
        "notes": [
            "This runner evaluates predictive association only.",
            "No portfolio return, transaction cost, execution, or risk simulation is performed.",
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-csv", required=True)
    parser.add_argument("--market-csv")
    parser.add_argument("--returns-csv")
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--rolling-window", type=int, default=20)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = run_backtest(
            args.factor_csv,
            args.market_csv,
            args.returns_csv,
            args.horizon,
            args.rolling_window,
        )
        exit_code = 0
    except Exception as exc:
        result = {"tool": "backtest_runner", "status": "fail", "backtest": {}, "errors": [str(exc)]}
        exit_code = 2
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
