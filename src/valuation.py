"""Python port of the Pine valuation algorithm v3.0.

The formulas, parameters and 100-tree GBM model are taken directly from
``reference/test_vard_algo_3_0.pine``. The implementation deliberately exposes
all intermediate columns so that dashboard values can be audited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import ROOT
from .utils import normalize_date_column


@dataclass(frozen=True)
class ValuationParameters:
    window_days: int = 20
    window_long: int = 180
    inner_period: int = 29
    outer_period: int = 11
    sma39_period: int = 39
    lag_period: int = 19
    w_double: float = 0.70
    w_sma39: float = 0.25
    w_lag: float = 0.05
    avv_period: int = 20
    avv_scale: float = 10.259784
    std_score_period: int = 35
    hist_ema_len: int = 19

    lin_w_gap: float = 0.564733
    lin_z_scale: float = 4.961122
    lin_a_cond: float = 0.051564
    lin_p_coef: float = 0.060012
    lin_quad: float = 0.028621
    lin_offset: float = 14.760836
    lin_scale: float = 3.324178
    lin_clip: float = 9.390153


class GBMModel:
    def __init__(self, payload: dict[str, list[int] | list[float]]) -> None:
        self.node_feat = np.asarray(payload["node_feat"], dtype=np.int32)
        self.node_thr = np.asarray(payload["node_thr"], dtype=np.float64)
        self.node_left = np.asarray(payload["node_left"], dtype=np.int32)
        self.node_right = np.asarray(payload["node_right"], dtype=np.int32)
        self.tree_root = np.asarray(payload["tree_root"], dtype=np.int32)
        n = len(self.node_feat)
        if not (len(self.node_thr) == len(self.node_left) == len(self.node_right) == n):
            raise ValueError("GBM node arrays have inconsistent lengths")

    @classmethod
    def load(cls, path: str | Path | None = None) -> "GBMModel":
        candidates = []
        if path is not None:
            candidates.append(Path(path))
        candidates.extend((ROOT / "data/model/gbm_model.json", ROOT / "src/model/gbm_model.json"))
        for candidate in candidates:
            if candidate.exists():
                return cls(json.loads(candidate.read_text(encoding="utf-8")))
        raise FileNotFoundError("gbm_model.json was not found")

    def evaluate(self, features: Iterable[float]) -> float:
        feature_values = np.asarray(tuple(features), dtype=np.float64)
        if feature_values.shape != (12,):
            raise ValueError(f"GBM expects 12 features, got {feature_values.shape}")
        result = 0.0
        for root in self.tree_root:
            node = int(root)
            for _ in range(51):
                feature_index = int(self.node_feat[node])
                if feature_index < 0:
                    break
                threshold = self.node_thr[node]
                node = int(self.node_left[node] if feature_values[feature_index] <= threshold else self.node_right[node])
            else:
                raise RuntimeError("GBM tree traversal exceeded 51 steps")
            result += float(self.node_thr[node])
        return result


def pine_ema(values: pd.Series, length: int) -> pd.Series:
    """Recursive EMA compatible with the formula documented for Pine ``ta.ema``.

    The accumulator starts at the first non-null source value. Null source rows
    remain null while the previous accumulator is preserved for the next valid
    observation.
    """

    alpha = 2.0 / (length + 1.0)
    source = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    output = np.full(len(source), np.nan, dtype=float)
    previous = np.nan
    for index, value in enumerate(source):
        if np.isnan(value):
            continue
        previous = value if np.isnan(previous) else alpha * value + (1.0 - alpha) * previous
        output[index] = previous
    return pd.Series(output, index=values.index, dtype="float64")


def rolling_percent_less(values: pd.Series, length: int) -> pd.Series:
    source = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    output = np.full(len(source), np.nan, dtype=float)
    for index in range(length, len(source)):
        current = source[index]
        if np.isnan(current):
            continue
        window = source[index - length + 1 : index + 1]
        valid = window[~np.isnan(window)]
        if valid.size:
            output[index] = float(np.sum(valid < current) / valid.size * 100.0)
    return pd.Series(output, index=values.index, dtype="float64")


def _compute_linear_score(
    gap: pd.Series,
    avv: pd.Series,
    hist_ema: pd.Series,
    z_gap: pd.Series,
    p: ValuationParameters,
) -> pd.Series:
    output = np.full(len(gap), np.nan, dtype=float)
    for index in range(len(gap)):
        g = gap.iat[index]
        a = avv.iat[index]
        h = hist_ema.iat[index]
        z = z_gap.iat[index]
        if pd.isna(g) or pd.isna(z) or pd.isna(h):
            continue
        gc = max(-p.lin_clip, min(p.lin_clip, float(g)))
        conditional = float(a) if not pd.isna(a) and float(g) * float(a) > 0 else 0.0
        base = (
            p.lin_w_gap * gc
            + (1.0 - p.lin_w_gap) * float(z) * p.lin_z_scale
            + p.lin_a_cond * conditional
            + p.lin_p_coef * (float(h) - 50.0)
        )
        curved = base + p.lin_quad * base * abs(base)
        output[index] = max(0.0, min(100.0, (curved + p.lin_offset) * p.lin_scale))
    return pd.Series(output, index=gap.index, dtype="float64")


def price_zone(score: float | None) -> str:
    if score is None or pd.isna(score):
        return "N/A"
    if score >= 80:
        return "Övervärderad"
    if score >= 60:
        return "Relativt dyr"
    if score >= 40:
        return "Neutral"
    if score >= 20:
        return "Relativt attraktiv"
    return "Undervärderad"


def calculate_valuation(
    frame: pd.DataFrame,
    *,
    model: GBMModel | None = None,
    params: ValuationParameters | None = None,
) -> pd.DataFrame:
    """Calculate all Pine v3.0 valuation fields for a daily price/EPS frame.

    Required columns are ``Date``, ``Close`` and ``EPS_TTM``. Other OHLC fields
    are preserved. EPS is expected to be point-in-time and already mapped to its
    effective trading date.
    """

    p = params or ValuationParameters()
    gbm = model or GBMModel.load()
    result = normalize_date_column(frame)
    for required in ("Close", "EPS_TTM"):
        if required not in result.columns:
            raise ValueError(f"Missing required column: {required}")

    close = pd.to_numeric(result["Close"], errors="coerce")
    eps = pd.to_numeric(result["EPS_TTM"], errors="coerce")
    pe = close.div(eps.where(eps != 0)).replace([np.inf, -np.inf], np.nan).ffill()
    result["PE_TTM"] = pe

    pe_min = pe.rolling(p.window_days, min_periods=p.window_days).min()
    pe_max = pe.rolling(p.window_days, min_periods=p.window_days).max()
    denominator = pe_max - pe_min
    hist_pct = ((pe - pe_min) / denominator * 100.0).where(denominator > 0).clip(0.0, 100.0)
    result["HistPct20"] = hist_pct
    hist_pct_ema = pine_ema(hist_pct, p.hist_ema_len)
    result["HistPctEMA19"] = hist_pct_ema

    pct_long = rolling_percent_less(pe, p.window_long)
    result["PctLong180"] = pct_long

    pe_inner = pe.rolling(p.inner_period, min_periods=p.inner_period).mean()
    pe_double = pe_inner.rolling(p.outer_period, min_periods=p.outer_period).mean()
    pe_sma39 = pe.rolling(p.sma39_period, min_periods=p.sma39_period).mean()
    pe_lag = pe.shift(p.lag_period)
    pe_ref = p.w_double * pe_double + p.w_sma39 * pe_sma39 + p.w_lag * pe_lag
    gap_pct = ((pe - pe_ref) / pe_ref * 100.0).where(pe_ref > 0)
    result["PE_Ref"] = pe_ref
    result["GapPct"] = gap_pct

    pe_sma_avv = pe.rolling(p.avv_period, min_periods=p.avv_period).mean()
    pe_std_avv = pe.rolling(p.avv_period, min_periods=p.avv_period).std(ddof=0)
    avv_z = ((pe - pe_sma_avv) / pe_std_avv).where(pe_std_avv > 0)
    avv_raw = p.avv_scale * avv_z
    result["AvvZ"] = avv_z
    result["AvvRaw"] = avv_raw

    pe_std_score = pe.rolling(p.std_score_period, min_periods=p.std_score_period).std(ddof=0)
    z_gap = ((pe - pe_ref) / pe_std_score).where(pe_std_score > 0)
    result["PEStd35"] = pe_std_score
    result["ZGap"] = z_gap

    linear = _compute_linear_score(gap_pct, avv_raw, hist_pct_ema, z_gap, p)
    result["LinearScore"] = linear

    features = pd.DataFrame(
        {
            "f0": gap_pct,
            "f1": avv_raw,
            "f2": hist_pct,
            "f3": hist_pct_ema,
            "f4": pct_long,
            "f5": z_gap,
            "f6": pe_std_score,
            "f7": gap_pct.shift(5),
            "f8": hist_pct_ema.shift(5),
            "f9": pct_long.shift(5),
            "f10": avv_raw.shift(5),
            "f11": z_gap.shift(5),
        }
    )
    can_run = features.notna().all(axis=1)
    boost = np.zeros(len(result), dtype=float)
    for index in np.flatnonzero(can_run.to_numpy()):
        boost[index] = gbm.evaluate(features.iloc[index].to_numpy(dtype=float))
    result["GBMBoost"] = boost
    result["CanRunGBM"] = can_run

    score = linear.copy()
    score.loc[can_run] = (linear.loc[can_run] + boost[can_run.to_numpy()]).clip(0.0, 100.0)
    result["Score"] = score.clip(0.0, 100.0)
    result["PriceZone"] = result["Score"].map(price_zone)
    return result
