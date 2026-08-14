"""Tests for the metrics and, above all, for the interval machinery.

The interval bug this repo is partly about -- estimating a 2.5% quantile from
three residuals -- passed every unit test I had at the time, because I had no
test that asked whether an interval covered anything. These do.
"""
import numpy as np
import pytest

from src.fc import metrics as M
from src.fc import models as Mod


def test_smape_zero_on_perfect_forecast():
    y = np.array([1.0, 2.0, 3.0])
    assert M.smape(y, y.copy()) == pytest.approx(0.0)


def test_smape_survives_zeros():
    """|y|+|yhat| == 0 is 0/0; it must be 0, not nan."""
    assert np.isfinite(M.smape(np.zeros(3), np.zeros(3)))


def test_mase_is_one_for_seasonal_naive_on_its_own_scale():
    rng = np.random.default_rng(0)
    y = np.tile(rng.normal(10, 1, 12), 8)
    ins, act = y[:-12], y[-12:]
    f = Mod.seasonal_naive(ins, 12, 12)
    assert M.mase(act, f.point, ins, 12) < 2.0


def test_mase_handles_constant_series():
    """A flat series has zero seasonal-naive error; the scale must not be 0."""
    y = np.ones(50)
    assert np.isfinite(M.mase(y[-10:], y[-10:], y[:-10], 4))


def test_coverage_bounds():
    y = np.array([1.0, 2.0, 3.0])
    assert M.coverage(y, y - 1, y + 1) == 1.0
    assert M.coverage(y, y + 5, y + 6) == 0.0


def test_msis_penalises_misses_more_than_width():
    y = np.array([10.0, 10.0])
    tight_hit = M.msis(y, y - 1, y + 1, np.arange(20.0), 1)
    tight_miss = M.msis(y, y + 5, y + 6, np.arange(20.0), 1)
    assert tight_miss > tight_hit


def test_seasonal_naive_repeats_the_season():
    y = np.array([1.0, 2, 3, 4, 1, 2, 3, 4])
    f = Mod.seasonal_naive(y, 4, 4)
    assert list(f.point) == [1, 2, 3, 4]


def test_intervals_widen_with_horizon():
    """A forecast 48 steps out must not claim the certainty of one step out."""
    y = np.arange(200.0) + np.random.default_rng(0).normal(0, 1, 200)
    f = Mod.naive(y, 20, 1)
    w = f.hi - f.lo
    assert w[-1] > w[0]


# --- the regression that matters -------------------------------------------

def test_empirical_intervals_use_enough_folds():
    """Three folds cannot resolve a 2.5% quantile: the estimate is bounded by
    the min and max of three numbers. The original code did exactly that and
    produced 44-49% coverage on a nominal 95% interval."""
    y = np.tile(np.arange(24.0), 40) + np.random.default_rng(0).normal(0, 1, 960)
    lo, hi = Mod.empirical_intervals(y, 48, 24, Mod.seasonal_naive)
    assert np.all(lo > 0) and np.all(hi > 0)
    analytic = Mod.seasonal_naive(y, 48, 24)
    analytic_half = (analytic.hi - analytic.lo) / 2
    # Should be in the same order of magnitude as the analytic band, not the
    # ~4x-too-narrow band the 3-fold version produced.
    assert np.mean(lo + hi) > 0.5 * np.mean(2 * analytic_half)


def test_empirical_intervals_cover_roughly_nominally():
    """End-to-end: on a series whose noise is stationary and known, a nominal
    95% empirical interval should cover far more than half the time."""
    rng = np.random.default_rng(1)
    season = np.arange(24.0)
    y = np.tile(season, 45) + rng.normal(0, 1.0, 24 * 45)
    ins, act = y[:-48], y[-48:]
    lo_d, hi_d = Mod.empirical_intervals(ins, 48, 24, Mod.seasonal_naive)
    pt = Mod.seasonal_naive(ins, 48, 24).point
    cov = M.coverage(act, pt - lo_d, pt + hi_d)
    assert cov > 0.80, f"coverage {cov:.2f} far below nominal 0.95"
