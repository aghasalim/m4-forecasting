"""Forecasters, each returning a point forecast and a 95% interval.

Every method here must produce an interval, including the naive ones. That is
deliberate: the usual pattern is to benchmark point accuracy against a naive
baseline and then quietly compare *intervals* only among the sophisticated
methods, which hides that a residual-quantile interval around a seasonal naive
forecast is often better calibrated than a model's analytic one.

Two families of interval:

- **analytic** -- from the model's own error variance, assuming the residuals
  are Gaussian and the model is correctly specified. Both assumptions are
  usually false, in the same direction: too narrow.
- **empirical** -- quantiles of actual backtest residuals at each horizon step.
  Assumes only that past errors resemble future ones, and widens naturally with
  horizon because the residuals do.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

warnings.filterwarnings("ignore")

Z95 = 1.959964


@dataclass
class Forecast:
    point: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    name: str


def _resid_sigma(y: np.ndarray, m: int) -> float:
    """In-sample seasonal-naive residual scale, used for naive intervals."""
    if len(y) > m:
        r = y[m:] - y[:-m]
    else:
        r = np.diff(y) if len(y) > 1 else np.array([0.0])
    s = float(np.std(r))
    return s if s > 0 and np.isfinite(s) else 1.0


def seasonal_naive(y: np.ndarray, h: int, m: int) -> Forecast:
    """Repeat the last full season. The baseline that is embarrassingly hard to
    beat on strongly seasonal data, and the one most write-ups omit."""
    if m <= 1 or len(y) < m:
        pt = np.repeat(y[-1], h)
    else:
        last = y[-m:]
        pt = np.array([last[i % m] for i in range(h)], dtype=float)
    s = _resid_sigma(y, m)
    # Random-walk-style widening: uncertainty grows with the square root of how
    # many seasons ahead we are, not flat across the horizon.
    steps = np.sqrt(1 + np.arange(h) // max(m, 1))
    band = Z95 * s * steps
    return Forecast(pt, pt - band, pt + band, "seasonal_naive")


def naive(y: np.ndarray, h: int, m: int) -> Forecast:
    pt = np.repeat(float(y[-1]), h)
    s = float(np.std(np.diff(y))) if len(y) > 1 else 1.0
    s = s if s > 0 and np.isfinite(s) else 1.0
    band = Z95 * s * np.sqrt(np.arange(1, h + 1))
    return Forecast(pt, pt - band, pt + band, "naive")


def naive2(y: np.ndarray, h: int, m: int) -> Forecast:
    """M4's official baseline: seasonally adjust, naive forecast, re-seasonalise.

    Every OWA in this repo is relative to this, so it is computed rather than
    taken from a paper.
    """
    if m > 1 and len(y) >= 2 * m:
        idx = np.arange(len(y))
        seas = np.array([np.mean(y[idx % m == k]) for k in range(m)])
        overall = np.mean(y)
        seas = seas - overall if overall == 0 else seas / overall
        seas = np.where(np.abs(seas) < 1e-8, 1.0, seas)
        deseas = y / seas[idx % m]
        pt = np.repeat(deseas[-1], h)
        fidx = (np.arange(len(y), len(y) + h)) % m
        pt = pt * seas[fidx]
    else:
        pt = np.repeat(float(y[-1]), h)
    s = _resid_sigma(y, m)
    band = Z95 * s * np.sqrt(np.arange(1, h + 1))
    return Forecast(pt, pt - band, pt + band, "naive2")


def theta(y: np.ndarray, h: int, m: int) -> Forecast:
    """The Theta method -- winner of M3, still competitive on M4.

    Implemented directly: deseasonalise, fit SES to the level plus half the
    linear drift, reseasonalise. Short enough to read, which matters more here
    than the extra fraction of a point a tuned library version would give.
    """
    n = len(y)
    seas = np.ones(m if m > 1 else 1)
    ys = y.astype(float)
    if m > 1 and n >= 2 * m:
        idx = np.arange(n)
        overall = np.mean(y)
        seas = np.array([np.mean(y[idx % m == k]) for k in range(m)])
        seas = seas / overall if overall != 0 else np.ones(m)
        seas = np.where(np.abs(seas) < 1e-8, 1.0, seas)
        ys = y / seas[idx % m]

    # SES with a fixed, conventional alpha -- fitting it per series on 700+
    # points is where Theta implementations diverge, and a fixed value keeps
    # this comparable across series.
    a = 0.2
    level = ys[0]
    for v in ys[1:]:
        level = a * v + (1 - a) * level
    t = np.arange(n)
    slope = np.polyfit(t, ys, 1)[0] if n > 2 else 0.0
    pt = level + 0.5 * slope * np.arange(1, h + 1)

    if m > 1 and n >= 2 * m:
        fidx = (np.arange(n, n + h)) % m
        pt = pt * seas[fidx]

    s = _resid_sigma(y, m)
    band = Z95 * s * np.sqrt(np.arange(1, h + 1))
    return Forecast(pt, pt - band, pt + band, "theta")


METHODS = {
    "naive": naive,
    "naive2": naive2,
    "seasonal_naive": seasonal_naive,
    "theta": theta,
}


MIN_FOLDS_FOR_QUANTILE = 12


def empirical_intervals(y: np.ndarray, h: int, m: int, fn, n_folds: int | None = None,
                        alpha: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Interval half-widths from backtest residuals, per horizon step.

    Rolling-origin: refit on a prefix, forecast h ahead, record the error at each
    step. The spread of those errors *is* the uncertainty, measured rather than
    assumed.

    The fold count is not a free parameter. A 2.5%/97.5% quantile estimated from
    k residuals cannot reach beyond their min and max, so with k=3 -- which is
    what this function originally used -- the "95% interval" is really a ~50%
    interval and measured coverage came out at 44-49%. It needs roughly 1/alpha
    points before the tail quantile means anything, hence the floor below; with
    fewer, it falls back to a Gaussian scaling of the residual spread, which
    uses the same residuals without pretending to resolve their tails.
    """
    folds = n_folds if n_folds is not None else max(1, (len(y) - max(2 * m, 10)) // h)
    folds = int(min(folds, 24))

    errs = []
    for k in range(folds, 0, -1):
        cut = len(y) - k * h
        if cut < max(2 * m, 10):
            continue
        f = fn(y[:cut], h, m)
        actual = y[cut : cut + h]
        if len(actual) == h:
            errs.append(actual - f.point)

    if len(errs) < 2:
        f = fn(y, h, m)
        half = (f.hi - f.lo) / 2
        return half, half

    E = np.vstack(errs)
    if len(errs) >= MIN_FOLDS_FOR_QUANTILE:
        lo_q = np.quantile(E, alpha / 2, axis=0)
        hi_q = np.quantile(E, 1 - alpha / 2, axis=0)
        return -lo_q, hi_q

    # Too few folds to resolve a tail: use the spread, not the extremes.
    sd = np.std(E, axis=0, ddof=1)
    bias = np.mean(E, axis=0)
    half = Z95 * np.maximum(sd, 1e-9)
    return half - bias, half + bias
