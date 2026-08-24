"""Draw the README figures from reports/*.csv.

Reads the saved summaries only -- no M4 download, no refit.

    python scripts/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

FREQUENCIES = ["Hourly", "Weekly"]
INTERVALS = {"analytic": "#b2182b", "empirical": "#2166ac"}
NOMINAL = 0.95


def summary(frequency: str) -> pd.DataFrame:
    return pd.read_csv(REPORTS / f"summary_{frequency}.csv")


def coverage(out: Path) -> Path:
    """Does a 95% interval actually contain the truth 95% of the time?

    This is the number the repository exists to report. Weekly analytic intervals
    land on 94.9%, essentially nominal. Everything on Hourly under-covers, worst
    case 79.1% for a nominal 95% -- and empirical intervals under-cover on Weekly
    too. A point forecast can be excellent while its interval is meaningless.
    """
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        table = summary(frequency)
        methods = sorted(table.method.unique())
        base = np.arange(len(methods))
        for offset, (interval, colour) in enumerate(INTERVALS.items()):
            rows = table[table.interval == interval].set_index("method").loc[methods]
            ax.bar(base + (offset - 0.5) * 0.38, rows.coverage95 * 100, 0.38,
                   label=interval, color=colour, edgecolor="0.3", lw=0.5)
        ax.axhline(NOMINAL * 100, color="0.2", ls="--", lw=1.6)
        ax.set_xticks(base)
        ax.set_xticklabels(methods, rotation=15, ha="right", fontsize=8)
        ax.set_ylim(70, 100)
        ax.set_title(f"{frequency}  (n={table.n.iloc[0]})", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("realised coverage of a 95% interval (%)")
    axes[0].legend(frameon=False, fontsize=9)
    axes[0].text(-0.4, NOMINAL * 100 + 0.4, "nominal 95%", fontsize=8, color="0.3")
    figure.suptitle(
        "Dashed line is what the interval promises. Only the Weekly analytic "
        "intervals reach it;\neverything on Hourly under-covers, by up to 16 points.",
        fontsize=10, y=0.02, color="0.35",
    )
    figure.tight_layout(rect=(0, 0.06, 1, 1))
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def point_vs_interval(out: Path) -> Path:
    """Ranking by point accuracy against ranking by interval quality.

    OWA is the M4 point-forecast metric; MSIS scores the interval. They do not
    order the methods the same way, so a competition won on OWA says little about
    whether the intervals were usable.
    """
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        table = summary(frequency)
        for interval, colour in INTERVALS.items():
            rows = table[table.interval == interval]
            ax.scatter(rows.OWA, rows.MSIS, s=90, color=colour, label=interval,
                       edgecolor="0.3", lw=0.5, alpha=0.85)
            for _, row in rows.iterrows():
                ax.annotate(row.method, (row.OWA, row.MSIS),
                            textcoords="offset points", xytext=(6, 4), fontsize=7,
                            color="0.35")
        ax.set_xlabel("OWA  (point accuracy, lower better)")
        ax.set_ylabel("MSIS  (interval quality, lower better)")
        ax.set_title(frequency, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=9)
    figure.suptitle(
        "If the two agreed, the points would fall on a rising line.",
        fontsize=10, y=0.02, color="0.35",
    )
    figure.tight_layout(rect=(0, 0.06, 1, 1))
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def coverage_width(out: Path) -> Path:
    """What the coverage costs in interval width.

    An interval can always be made to cover by making it wider. Plotting the two
    together shows which methods buy coverage honestly and which just widen --
    analytic intervals on Hourly are up to five times wider for less coverage than
    the empirical ones.
    """
    figure, ax = plt.subplots(figsize=(9.5, 5.0))
    markers = {"Hourly": "o", "Weekly": "s"}
    for frequency in FREQUENCIES:
        table = summary(frequency)
        for interval, colour in INTERVALS.items():
            rows = table[table.interval == interval]
            ax.scatter(rows.width, rows.coverage95 * 100, s=90, color=colour,
                       marker=markers[frequency], edgecolor="0.3", lw=0.5,
                       alpha=0.85, label=f"{frequency}, {interval}")
    ax.axhline(NOMINAL * 100, color="0.2", ls="--", lw=1.4)
    ax.set_xlabel("mean interval width")
    ax.set_ylabel("realised coverage (%)")
    ax.set_title(
        "Up and to the left is better. Analytic intervals on Hourly are far wider\n"
        "and still cover less than the empirical ones.",
        fontsize=10,
    )
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def per_series(out: Path) -> Path:
    """The spread behind each aggregate number.

    Every value in the summary tables is a mean over hundreds of series. The
    distributions overlap heavily, which is worth seeing before reading a
    two-decimal ranking as settled.
    """
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        raw = pd.read_csv(REPORTS / f"raw_{frequency}.csv")
        raw = raw[raw.interval == "empirical"]
        methods = sorted(raw.method.unique())
        data = [raw[raw.method == m].mase.clip(upper=raw.mase.quantile(0.99))
                for m in methods]
        parts = ax.boxplot(data, tick_labels=methods, showfliers=False,
                           patch_artist=True)
        for patch in parts["boxes"]:
            patch.set_facecolor("#9ecae1")
            patch.set_edgecolor("0.3")
        ax.axhline(1.0, color="#b2182b", ls="--", lw=1.3)
        ax.set_ylabel("MASE per series")
        ax.tick_params(axis="x", rotation=15, labelsize=8)
        ax.set_title(f"{frequency}  (n={len(raw[raw.method == methods[0]])})",
                     fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    figure.suptitle(
        "Red line is MASE=1, the seasonal-naive reference. Whiskers clipped at "
        "the 99th percentile.",
        fontsize=10, y=0.02, color="0.35",
    )
    figure.tight_layout(rect=(0, 0.06, 1, 1))
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def interval_gain(out: Path) -> Path:
    """What switching from analytic to empirical intervals buys, per method."""
    figure, ax = plt.subplots(figsize=(10, 4.6))
    labels, deltas = [], []
    for frequency in FREQUENCIES:
        table = summary(frequency)
        analytic = table[table.interval == "analytic"].set_index("method")
        empirical = table[table.interval == "empirical"].set_index("method")
        for method in sorted(analytic.index):
            labels.append(f"{frequency[:1]}·{method}")
            deltas.append(empirical.loc[method, "MSIS"] - analytic.loc[method, "MSIS"])
    positions = np.arange(len(labels))
    colours = ["#1a9850" if d < 0 else "#b2182b" for d in deltas]
    ax.barh(positions, deltas, color=colours, edgecolor="0.3", lw=0.5)
    ax.axvline(0, color="0.2", lw=1.1)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("change in MSIS from analytic to empirical (negative is better)")
    improved = sum(1 for d in deltas if d < 0)
    ax.set_title(
        f"Empirical intervals improve MSIS in {improved} of {len(deltas)} "
        "method-frequency pairs.",
        fontsize=10,
    )
    ax.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in (
        coverage(FIGURES / "coverage.png"),
        point_vs_interval(FIGURES / "point-vs-interval.png"),
        coverage_width(FIGURES / "coverage-width.png"),
        per_series(FIGURES / "per-series.png"),
        interval_gain(FIGURES / "interval-gain.png"),
    ):
        print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
