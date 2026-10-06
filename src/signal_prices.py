"""Next-session score boundaries, keeping the historical observations and EPS fixed."""
from functools import lru_cache
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .config import ROOT
from .utils import write_json_atomic
from .valuation import GBMModel, ValuationParameters, calculate_valuation


class _ZeroModel:
    def evaluate(self, features):
        return 0.0


@lru_cache(maxsize=1)
def _negative_model():
    return GBMModel.load(ROOT / "data/model/negpe_gbm_model.json")


def _batch_evaluate(model, features):
    if len(features) == 1:
        return np.array([model.evaluate(features[0])])
    result = np.zeros(len(features))
    for root in model.tree_root:
        nodes = np.full(len(features), root, dtype=int)
        for _ in range(51):
            feature = model.node_feat[nodes]
            active = feature >= 0
            if not active.any():
                break
            indices = np.flatnonzero(active)
            current = nodes[indices]
            nodes[indices] = np.where(
                features[indices, feature[indices]] <= model.node_thr[current],
                model.node_left[current], model.node_right[current],
            )
        else:
            raise RuntimeError("GBM tree traversal exceeded 51 steps")
        result += model.node_thr[nodes]
    return result


class NextCloseScore:
    """Calculate only the new row; EMA and lagged features use the entire history."""
    def __init__(self, frame, model, negative_model=None):
        self.history = calculate_valuation(frame, model=_ZeroModel(), negative_model=_ZeroModel())
        self.pe = self.history.PE_TTM.to_numpy(dtype=float)
        self.eps = float(frame.EPS_TTM.iloc[-1])
        self.model = model if self.eps > 0 else negative_model or _negative_model()

    def __call__(self, prices):
        v, pe, p = self.history, self.pe, ValuationParameters()
        prices = np.asarray(prices, dtype=float)
        if len(pe) < (180 if self.eps > 0 else 39) or not np.isfinite(self.eps) or self.eps == 0:
            return np.full(len(prices), np.nan)
        x = prices / self.eps
        def stats(n):
            previous = pe[-(n - 1):]
            # Centre the sums to avoid cancellation for a nearly constant P/E.
            anchor = previous.mean()
            differences = previous - anchor
            delta = x - anchor
            mean_delta = (differences.sum() + delta) / n
            variance = ((differences ** 2).sum() + delta ** 2) / n - mean_delta ** 2
            return anchor + mean_delta, np.sqrt(np.maximum(0, variance))
        with np.errstate(divide="ignore", invalid="ignore"):
            low = np.minimum(pe[-19:].min(), x)
            high = np.maximum(pe[-19:].max(), x)
            hist = np.clip((x - low) / (high - low) * 100, 0, 100)
            ema = .1 * hist + .9 * v.HistPctEMA19.iloc[-1]
            prior_long = pe[-179:][np.isfinite(pe[-179:])]
            percentile = (prior_long[:, None] < x).sum(axis=0) / (len(prior_long) + 1) * 100
            inner = (pe[-28:].sum() + x) / 29
            prior_inner = pd.Series(pe).rolling(29).mean().iloc[-10:].sum()
            double = (prior_inner + inner) / 11
            sma = (pe[-38:].sum() + x) / 39
            reference = .70 * double + .25 * sma + .05 * pe[-19]
            gap = (x - reference) / reference * 100
            mean, std = stats(20)
            avv = p.avv_scale * (x - mean) / std
            _, std35 = stats(35)
            z = (x - reference) / std35
            if self.eps > 0:
                gap = np.where(reference > 0, gap, np.nan)
                base = (p.lin_w_gap * np.clip(gap, -p.lin_clip, p.lin_clip)
                        + (1 - p.lin_w_gap) * z * p.lin_z_scale
                        + p.lin_a_cond * np.where(gap * avv > 0, avv, 0)
                        + p.lin_p_coef * (ema - 50))
                linear = np.clip((base + p.lin_quad * base * np.abs(base) + p.lin_offset) * p.lin_scale, 0, 100)
                lag = v.iloc[-5]
                lag_gap = lag.GapPct if lag.PE_Ref > 0 else np.nan
                features = np.column_stack([gap, avv, hist, ema, percentile, z, std35,
                    *[np.full(len(x), value) for value in
                      [lag_gap, lag.HistPctEMA19, lag.PctLong180, lag.AvvRaw, lag.ZGap]]])
            else:
                low60 = np.minimum(pe[-59:].min(), x)
                high60 = np.maximum(pe[-59:].max(), x)
                hist60 = np.clip((x - low60) / (high60 - low60) * 100, 0, 100)
                features = np.column_stack([np.clip(gap + 50, 0, 100), np.clip(avv + 50, 0, 100),
                                           np.abs(x), x - pe[-5], std, hist60])
                linear = np.zeros(len(x))
        ready = np.isfinite(features).all(axis=1) & (prices > 0)
        score = np.full(len(x), np.nan)
        score[ready] = np.clip(linear[ready] + _batch_evaluate(self.model, features[ready]), 0, 100)
        return score


def find_boundary(predict, last_close, side):
    """Find the nearest sampled crossing and refine it, without assuming monotonicity."""
    grid = np.unique(np.r_[np.geomspace(last_close * .25, last_close * 4, 2001),
                           np.linspace(last_close * .7, last_close * 1.3, 2401)])
    values = predict(grid)
    inside = values < 1 if side == "buy" else values > 99
    valid = np.isfinite(values)
    crossings = np.flatnonzero((inside[1:] != inside[:-1]) & valid[1:] & valid[:-1])
    if not len(crossings):
        return None
    index = min(crossings, key=lambda i: abs((grid[i] + grid[i + 1]) / 2 - last_close))
    left, right = grid[index], grid[index + 1]
    left_inside = bool(inside[index])
    for _ in range(35):
        mid = (left + right) / 2
        value = float(predict([mid])[0])
        if not np.isfinite(value):
            return None
        mid_inside = value < 1 if side == "buy" else value > 99
        if mid_inside == left_inside:
            left = mid
        else:
            right = mid
    price = left if left_inside else right
    # Keep a small margin inside the region: different floating-point reductions
    # in the full historical calculation must not flip a strict <1 / >99 test.
    inset = price * (1 - 1e-8 if left_inside else 1 + 1e-8)
    inset_score = float(predict([inset])[0])
    if np.isfinite(inset_score) and (inset_score < 1 if side == "buy" else inset_score > 99):
        price = inset
    return {"price": float(price), "score": float(predict([price])[0]),
            "direction": "below" if left_inside else "above",
            "change_pct": float((price / last_close - 1) * 100),
            "multiple_crossings": len(crossings) > 1}


def write_signal_prices(frames, model, generated_at, path: Path):
    payload = {"generated_at": generated_at, "assumption": "unchanged_eps",
               "search_range_factors": [.25, 4], "stocks": {}}
    for ticker, frame in frames.items():
        if model is None or frame.empty:
            continue
        eps = frame.EPS_TTM.iloc[-1]
        close = float(frame.Close.iloc[-1])
        if not np.isfinite(eps) or eps == 0 or close <= 0:
            continue
        day = pd.Timestamp(frame.Date.iloc[-1]).normalize()
        sessions = xcals.get_calendar("XSTO", start=day, end=day + pd.Timedelta(days=20)).sessions
        sessions = sessions.tz_localize(None) if sessions.tz is not None else sessions
        target = sessions[sessions.searchsorted(day, side="right")]
        predict = NextCloseScore(frame, model)
        payload["stocks"][ticker] = {"as_of": day.date().isoformat(), "session": target.date().isoformat(),
                                    "buy": find_boundary(predict, close, "buy"),
                                    "sell": find_boundary(predict, close, "sell")}
    write_json_atomic(path, payload)
    return payload
