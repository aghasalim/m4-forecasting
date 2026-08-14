"""Forecast accuracy and, more importantly, forecast *honesty*.

Point-accuracy metrics answer "how close was the line". They say nothing about
whether the uncertainty around that line was truthful, and uncertainty is what a
forecast is actually used for -- you staff a warehouse against the upper bound,
not the mean. So coverage is treated here as a first-class metric rather than a
diagnostic: a nominal 95% interval that contains the truth 70% of the time is
not a slightly-imperfect interval, it is a wrong one, and nothing in sMAPE or
MASE will tell you.

Metric definitions follow the M4 competition so the numbers are comparable to
published results rather than to my own conventions.
"""
from __future__ import annotations

import numpy as np


def smape(y: np.ndarray, yhat: np.ndarray) -> float:
    """M4's symmetric MAPE, in percent.

    Symmetric in name only -- it still penalises over- and under-forecasting
    unequally -- but it is the competition definition and changing it would make
    these numbers incomparable to everyone else's.
    """
    denom = np.abs(y) + np.abs(yhat)
    # Where both are zero the term is defined as 0, not 0/0.
    out = np.where(denom == 0, 0.0, 2.0 * np.abs(y - yhat) / np.where(denom == 0, 1, denom))
    return float(100.0 * np.mean(out))


def mase(y: np.ndarray, yhat: np.ndarray, insample: np.ndarray, m: int) -> float:
    """Mean absolute scaled error.

    Scaled by the in-sample seasonal-naive error, which makes it comparable
    across series of wildly different magnitude -- the reason it is preferred
    over MAPE on a 100k-series benchmark. MASE = 1 means "no better than
    predicting last season".
    """
    if len(insample) <= m:
        scale = np.mean(np.abs(np.diff(insample))) if len(insample) > 1 else 1.0
    else:
        scale = np.mean(np.abs(insample[m:] - insample[:-m]))
    if scale == 0 or not np.isfinite(scale):
        scale = 1.0
    return float(np.mean(np.abs(y - yhat)) / scale)


def owa(smape_m: float, mase_m: float, smape_base: float, mase_base: float) -> float:
    """Overall Weighted Average, M4's headline metric: the mean of the two
    errors each divided by the Naive2 baseline's. 1.0 means "exactly as good as
    Naive2"; below 1 beats it."""
    a = smape_m / smape_base if smape_base else np.nan
    b = mase_m / mase_base if mase_base else np.nan
    return float((a + b) / 2)


# --- interval honesty ------------------------------------------------------

def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Fraction of actuals inside the interval. Compare against nominal."""
    return float(np.mean((y >= lo) & (y <= hi)))


def interval_width(lo: np.ndarray, hi: np.ndarray, insample: np.ndarray, m: int) -> float:
    """Mean width, scaled like MASE so it is comparable across series.

    Reported alongside coverage because the two trade off trivially: any
    coverage target is reachable by widening the interval until it is useless.
    A method is only better if it achieves coverage at a *narrower* width.
    """
    if len(insample) > m:
        scale = np.mean(np.abs(insample[m:] - insample[:-m]))
    else:
        scale = np.mean(np.abs(np.diff(insample))) if len(insample) > 1 else 1.0
    if scale == 0 or not np.isfinite(scale):
        scale = 1.0
    return float(np.mean(hi - lo) / scale)


def msis(y: np.ndarray, lo: np.ndarray, hi: np.ndarray, insample: np.ndarray,
         m: int, alpha: float = 0.05) -> float:
    """Mean Scaled Interval Score -- M4's official uncertainty metric.

    Width plus a penalty for each miss, scaled by seasonal-naive error. Unlike
    raw coverage it cannot be gamed by widening: the width term charges for it.
    """
    if len(insample) > m:
        scale = np.mean(np.abs(insample[m:] - insample[:-m]))
    else:
        scale = np.mean(np.abs(np.diff(insample))) if len(insample) > 1 else 1.0
    if scale == 0 or not np.isfinite(scale):
        scale = 1.0
    width = hi - lo
    below = (2.0 / alpha) * (lo - y) * (y < lo)
    above = (2.0 / alpha) * (y - hi) * (y > hi)
    return float(np.mean(width + below + above) / scale)
