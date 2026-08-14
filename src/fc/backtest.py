"""Evaluate every method on M4's official holdout, points and intervals together.

The holdout is the competition's own: the last h observations of each series,
never seen during fitting. That makes these numbers directly comparable to
published M4 results instead of to a split I invented.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import metrics as M
from . import models as Mod

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

# M4's seasonal periods and horizons.
SPEC = {"Hourly": (24, 48), "Weekly": (1, 13)}


def load(freq: str) -> tuple[list[np.ndarray], np.ndarray, int, int]:
    m, h = SPEC[freq]
    tr = pd.read_csv(DATA / f"{freq}-train.csv")
    te = pd.read_csv(DATA / f"{freq}-test.csv")
    series = [r[~np.isnan(r)].astype(float) for r in tr.iloc[:, 1:].to_numpy(dtype=float)]
    test = te.iloc[:, 1:].to_numpy(dtype=float)
    return series, test, m, h


def run(freq: str, limit: int | None = None) -> pd.DataFrame:
    series, test, m, h = load(freq)
    if limit:
        series, test = series[:limit], test[:limit]
    print(f"{freq}: {len(series)} series, m={m}, h={h}")

    rows = []
    for i, (y, actual) in enumerate(zip(series, test)):
        actual = actual[~np.isnan(actual)][:h]
        if len(actual) < h or len(y) < 2 * m + 2:
            continue
        base = Mod.naive2(y, h, m)
        s_base = M.smape(actual, base.point)
        m_base = M.mase(actual, base.point, y, m)

        for name, fn in Mod.METHODS.items():
            f = fn(y, h, m)
            rec = {
                "series": i, "method": name,
                "smape": M.smape(actual, f.point),
                "mase": M.mase(actual, f.point, y, m),
                "cover95": M.coverage(actual, f.lo, f.hi),
                "width": M.interval_width(f.lo, f.hi, y, m),
                "msis": M.msis(actual, f.lo, f.hi, y, m),
                "interval": "analytic",
            }
            rec["owa"] = M.owa(rec["smape"], rec["mase"], s_base, m_base)
            rows.append(rec)

            # Same point forecast, empirically-derived interval. Isolates the
            # interval construction from the forecast quality.
            dlo, dhi = Mod.empirical_intervals(y, h, m, fn)
            lo, hi = f.point - dlo, f.point + dhi
            rows.append({
                "series": i, "method": name,
                "smape": rec["smape"], "mase": rec["mase"], "owa": rec["owa"],
                "cover95": M.coverage(actual, lo, hi),
                "width": M.interval_width(lo, hi, y, m),
                "msis": M.msis(actual, lo, hi, y, m),
                "interval": "empirical",
            })

    df = pd.DataFrame(rows)
    REPORTS.mkdir(exist_ok=True)
    df.to_csv(REPORTS / f"raw_{freq}.csv", index=False)
    return df


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["method", "interval"]).agg(
        sMAPE=("smape", "mean"), MASE=("mase", "mean"), OWA=("owa", "mean"),
        coverage95=("cover95", "mean"), width=("width", "mean"), MSIS=("msis", "mean"),
        n=("series", "nunique"),
    ).round(4).reset_index()
    return g.sort_values(["interval", "OWA"])


def main() -> None:
    import sys

    freqs = sys.argv[1:] or ["Hourly", "Weekly"]
    all_summ = {}
    for freq in freqs:
        df = run(freq)
        s = summarise(df)
        print(f"\n=== {freq} ===")
        print(s.to_string(index=False))
        all_summ[freq] = s.to_dict(orient="records")
        s.to_csv(REPORTS / f"summary_{freq}.csv", index=False)
    (REPORTS / "summary.json").write_text(json.dumps(all_summ, indent=2))
    print(f"\n-> {REPORTS}")


if __name__ == "__main__":
    main()
