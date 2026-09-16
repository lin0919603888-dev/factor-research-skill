"""Predictive metric calculations for factor research."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _safe_mean(values: pd.Series) -> float | None:
    clean = values.dropna()
    return float(clean.mean()) if not clean.empty else None


def _safe_icir(values: pd.Series) -> float | None:
    clean = values.dropna().astype(float)
    if len(clean) < 2:
        return None
    standard_deviation = float(clean.std(ddof=0))
    return float(clean.mean() / standard_deviation) if standard_deviation > 0 else None


def _cross_sectional_ics(frame: pd.DataFrame, method: str) -> pd.Series:
    """Compute one IC per timestamp using repeated cross-sections."""
    values: dict[object, float] = {}
    for timestamp, group in frame.groupby("date", sort=True, dropna=False):
        if len(group) < 2 or group["factor"].nunique() < 2 or group["forward_return"].nunique() < 2:
            continue
        if method == "pearson":
            correlation = float(group["factor"].corr(group["forward_return"], method="pearson"))
        else:
            correlation = float(group["factor"].corr(group["forward_return"], method="spearman"))
        if pd.notna(correlation):
            values[timestamp] = correlation
    return pd.Series(values, name=f"{method}_ic")


def _rolling_time_series_ics(frame: pd.DataFrame, window: int) -> tuple[pd.Series, pd.Series]:
    """Compute rolling single-series ICs when no cross-section keys are supplied."""

    pearson = frame["factor"].rolling(window, min_periods=window).corr(frame["forward_return"])
    pearson.name = "rolling_pearson_ic"

    def rank_correlation(values: np.ndarray) -> float:
        factor_values = values[:, 0]
        return_values = values[:, 1]
        if np.std(factor_values) == 0 or np.std(return_values) == 0:
            return np.nan
        return float(pd.Series(factor_values).corr(pd.Series(return_values), method="spearman"))

    paired = frame[["factor", "forward_return"]].to_numpy()
    rolling_values = [
        rank_correlation(paired[index - window:index])
        if index >= window and not np.isnan(paired[index - window:index]).any()
        else np.nan
        for index in range(1, len(frame) + 1)
    ]
    spearman = pd.Series(rolling_values, index=frame.index, name="rolling_spearman_ic")
    return pearson, spearman


def calculate_metrics(
    observations: pd.DataFrame,
    rolling_window: int = 20,
) -> dict[str, Any]:
    """Calculate program-derived IC statistics.

    With `date` repeated across observations, metrics use conventional
    cross-sectional ICs. Without a cross-section, rolling single-series
    correlations provide explicit, but weaker, time-series diagnostics.
    """

    if rolling_window < 2:
        raise ValueError("rolling_window must be at least 2.")
    required = {"factor", "forward_return"}
    if not required.issubset(observations.columns):
        missing = sorted(required.difference(observations.columns))
        raise ValueError(f"Missing metric input columns: {missing}.")

    total_observations = int(len(observations))
    clean = observations.dropna(subset=["factor", "forward_return"]).copy()
    if clean.empty:
        return {
            "IC": None,
            "RankIC": None,
            "ICIR": None,
            "RankICIR": None,
            "total_observations": total_observations,
            "valid_observations": 0,
            "ic_observations": 0,
            "IC_positive_ratio": None,
            "method": None,
            "rolling_window": rolling_window if "date" not in clean else None,
        }

    has_cross_section = (
        "date" in clean.columns
        and len(clean) > 1
        and int(clean.groupby("date", dropna=False).size().max()) > 1
    )
    if has_cross_section:
        ic_series = _cross_sectional_ics(clean, "pearson")
        rank_ic_series = _cross_sectional_ics(clean, "spearman")
        method = "cross_sectional"
    else:
        clean = clean.drop(columns=["date"], errors="ignore").reset_index(drop=True)
        ic_series, rank_ic_series = _rolling_time_series_ics(clean, rolling_window)
        method = "rolling_time_series"

    result = {
        "IC": _safe_mean(ic_series),
        "RankIC": _safe_mean(rank_ic_series),
        "ICIR": _safe_icir(ic_series),
        "RankICIR": _safe_icir(rank_ic_series),
        "total_observations": total_observations,
        "valid_observations": int(len(clean)),
        "ic_observations": int(ic_series.notna().sum()),
        "IC_positive_ratio": (
            float((ic_series.dropna() > 0).mean()) if ic_series.notna().any() else None
        ),
        "method": method,
        "rolling_window": rolling_window if method == "rolling_time_series" else None,
    }
    return result
