"""Draw the README figures and the coverage animation from reports/.

Reads the committed summary and per-series tables only. No M4 download, no
refit, so a figure can never disagree with a number quoted in the README.

    python scripts/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
from PIL import Image

from style import PALETTE, titled

# Keeps the minus sign on a tick label a plain ASCII hyphen.
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

FREQUENCIES = ["Hourly", "Weekly"]
# M4's own horizons for these two subsets, not something measured here.
HORIZON = {"Hourly": 48, "Weekly": 13}
NOMINAL = 95.0
METRICS = ["sMAPE", "MASE", "OWA", "coverage95", "width", "MSIS"]

# Red is the interval the model hands you, blue the one measured from backtest
# residuals. The same two colours in every figure, so they are learned once.
ANALYTIC, EMPIRICAL = PALETTE[1], PALETTE[0]
HALO = [patheffects.withStroke(linewidth=2.6, foreground="white")]
LEGEND = [
    Line2D([], [], color=ANALYTIC, marker="o", linestyle="none", markersize=8,
           label="analytic interval, from the model"),
    Line2D([], [], color=EMPIRICAL, marker="o", linestyle="none", markersize=8,
           label="empirical interval, from backtest residuals"),
]


def summary(frequency: str) -> pd.DataFrame:
    """The committed summary, with methods reporting identical numbers merged.

    Weekly is m=1 in M4's setup, so naive, naive2 and seasonal_naive are the
    same forecast and the table repeats one row three times. Merging them into
    one labelled row keeps every number and stops three identical dots from
    landing on top of each other.
    """
    table = pd.read_csv(REPORTS / f"summary_{frequency}.csv")
    signature = {method: rows.sort_values("interval")[METRICS].to_numpy().tobytes()
                 for method, rows in table.groupby("method")}
    table["label"] = table.method.map(
        {method: " = ".join(sorted(k for k, v in signature.items() if v == sig))
         for method, sig in signature.items()})
    table["coverage"] = table.coverage95 * 100
    return table.drop_duplicates(["interval", "label"])


def per_series(frequency: str) -> pd.DataFrame:
    """Per-series rows, one representative per merged label.

    The dropped methods are the Weekly duplicates, whose per-series rows are
    identical to the row kept, so nothing measured is lost.
    """
    kept = summary(frequency).drop_duplicates("method").set_index("method").label
    raw = pd.read_csv(REPORTS / f"raw_{frequency}.csv")
    # Point accuracy does not depend on the interval construction, so one of the
    # two interval blocks gives every series exactly once.
    raw = raw[raw.interval == "empirical"].copy()
    raw["label"] = raw.method.map(kept)
    return raw.dropna(subset=["label"])


def _paired(frequency: str):
    """Analytic and empirical rows for one frequency, aligned and best first."""
    table = summary(frequency)
    analytic = table[table.interval == "analytic"].sort_values("OWA").set_index("label")
    empirical = table[table.interval == "empirical"].set_index("label").loc[analytic.index]
    return analytic, empirical


def _log_x(ax, ticks) -> None:
    """Log x axis with plain numbers on it rather than powers of ten."""
    ax.set_xscale("log")
    ax.set_xticks(ticks)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(plt.NullFormatter())


def coverage(out: Path) -> Path:
    """Realised coverage against the 95% every method advertises."""
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.4), sharex=True)
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        analytic, empirical = _paired(frequency)
        y = np.arange(len(analytic))[::-1]
        left = np.minimum(analytic.coverage, empirical.coverage)
        right = np.maximum(analytic.coverage, empirical.coverage)
        ax.hlines(y, left, right, color="#c8c8c8", lw=2.2, zorder=1)
        ax.scatter(analytic.coverage, y, s=85, color=ANALYTIC, zorder=3)
        ax.scatter(empirical.coverage, y, s=85, color=EMPIRICAL, zorder=3)
        for row, low, high in zip(y, left, right, strict=True):
            ax.annotate(f"{low:.1f}", (low, row), xytext=(-7, 0), fontsize=8.5,
                        textcoords="offset points", ha="right", va="center",
                        color="#5a5a5a", path_effects=HALO)
            ax.annotate(f"{high:.1f}", (high, row), xytext=(7, 0), fontsize=8.5,
                        textcoords="offset points", ha="left", va="center",
                        color="#5a5a5a", path_effects=HALO)
        ax.axvline(NOMINAL, color="#333333", linestyle="--", linewidth=1.2, zorder=2)
        ax.set_yticks(y)
        ax.set_yticklabels(analytic.index, fontsize=9.5)
        ax.set_ylim(-0.8, len(analytic) - 0.2)
        ax.set_xlim(74.5, 101.5)
        ax.set_xlabel("realised coverage (% of held-out points inside the interval)")
        ax.grid(axis="y", visible=False)

    axes[0].text(NOMINAL - 0.6, 0.02, "nominal 95%", transform=axes[0].get_xaxis_transform(),
                 fontsize=9, color="#333333", ha="right", va="bottom")
    titled(axes[0], "Not one Hourly interval covers what it promises",
           f"414 series, {HORIZON['Hourly']} held-out steps each; a pair is one forecast "
           "under two interval constructions")
    titled(axes[1], "The same analytic construction is honest on Weekly",
           f"359 series, {HORIZON['Weekly']} steps each; m=1 makes three of the four "
           "methods identical")
    figure.legend(handles=LEGEND, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.0))
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    figure.savefig(out)
    plt.close(figure)
    return out


def coverage_width(out: Path) -> Path:
    """What the coverage costs in width. Up and to the left is better."""
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    ticks = {"Hourly": [4, 6, 10, 20, 40, 70], "Weekly": [12, 14, 16, 18]}
    # Hand placed so a label never lands on another method's marker.
    offsets = {
        "seasonal_naive": (11, 0, "left", "center"),
        "naive2": (0, -15, "center", "top"),
        "theta": (0, 12, "center", "bottom"),
        "naive": (-11, -5, "right", "center"),
        "naive = naive2 = seasonal_naive": (8, 11, "right", "bottom"),
    }
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        analytic, empirical = _paired(frequency)
        for label in analytic.index:
            a, e = analytic.loc[label], empirical.loc[label]
            ax.annotate("", xy=(e.width, e.coverage), xytext=(a.width, a.coverage),
                        arrowprops={"arrowstyle": "->", "color": "#d2d2d2", "lw": 1.4},
                        zorder=1)
            dx, dy, ha, va = offsets[label]
            ax.annotate(label, (a.width, a.coverage), xytext=(dx, dy), fontsize=8.8,
                        textcoords="offset points", ha=ha, va=va, color="#5a5a5a",
                        path_effects=HALO)
        ax.scatter(analytic.width, analytic.coverage, s=85, color=ANALYTIC, zorder=3)
        ax.scatter(empirical.width, empirical.coverage, s=85, color=EMPIRICAL, zorder=3)
        ax.axhline(NOMINAL, color="#333333", linestyle="--", linewidth=1.2, zorder=2)
        _log_x(ax, ticks[frequency])
        ax.set_xlabel("mean interval width (units of the series, log axis)")
    axes[0].set_xlim(3.6, 82)
    axes[1].set_xlim(11.2, 19)
    axes[0].set_ylim(76, 99)
    axes[0].set_ylabel("realised coverage (%)")
    for ax in axes:
        ax.text(0.01, NOMINAL + 0.3, "nominal 95%", transform=ax.get_yaxis_transform(),
                fontsize=9, color="#333333", ha="left", va="bottom")
    titled(axes[0], "Coming close to nominal on Hourly costs 13 times the width",
           "the arrow runs from the model interval to the residual one; the point forecast "
           "is the same at both ends")
    titled(axes[1], "On Weekly nominal costs 39% more width, not 13 times",
           "three of the four Weekly methods are the same forecast, so they share a point")
    figure.legend(handles=LEGEND, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.0))
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    figure.savefig(out)
    plt.close(figure)
    return out


def point_vs_interval(out: Path) -> Path:
    """Ranking by point accuracy against ranking by interval quality."""
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        rows = summary(frequency)
        rows = rows[rows.interval == "empirical"]
        owa = rows.OWA.rank(method="min").to_numpy()
        msis = rows.MSIS.rank(method="min").to_numpy()
        for label, left, right, a, b in zip(rows.label, owa, msis, rows.OWA, rows.MSIS,
                                            strict=True):
            moved = left != right
            ax.plot([0, 1], [left, right], marker="o", markersize=7,
                    color=ANALYTIC if moved else "#b0b0b0", lw=2.4 if moved else 1.6,
                    zorder=3 if moved else 2)
            ax.annotate(f"{label}   {a:.2f}", (0, left), xytext=(-9, 0), fontsize=9,
                        textcoords="offset points", ha="right", va="center", color="#444444")
            ax.annotate(f"{b:.1f}", (1, right), xytext=(9, 0), fontsize=9,
                        textcoords="offset points", ha="left", va="center", color="#444444")
        ax.set_xlim(-0.06 * (max(map(len, rows.label)) + 8), 1.35)
        ax.set_ylim(len(rows) + 0.55, 0.45)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["rank by OWA\n(point accuracy)", "rank by MSIS\n(interval quality)"])
        ax.set_yticks(range(1, len(rows) + 1))
        ax.set_yticklabels([f"{i}." for i in range(1, len(rows) + 1)])
        ax.grid(visible=False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(length=0)
    titled(axes[0], "The worst point forecast has the second best interval",
           "Hourly, empirical intervals; a red line is a method the two metrics rank "
           "differently")
    titled(axes[1], "On Weekly the two metrics agree",
           "the number by each dot is the metric itself, and both are lower is better")
    figure.tight_layout()
    figure.savefig(out)
    plt.close(figure)
    return out


def spread(out: Path) -> Path:
    """The per-series spread behind each aggregate number."""
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    for ax, frequency in zip(axes, FREQUENCIES, strict=True):
        raw = per_series(frequency)
        order = raw.groupby("label").mase.mean().sort_values().index
        y = np.arange(len(order))[::-1]
        for row, label in zip(y, order, strict=True):
            values = raw[raw.label == label].mase
            lo, q1, med, q3, hi = values.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
            ax.hlines(row, lo, hi, color=EMPIRICAL, lw=1.6, alpha=0.75)
            ax.hlines(row, q1, q3, color=EMPIRICAL, lw=6.0, alpha=0.35)
            ax.plot([med], [row], "o", color=EMPIRICAL, markersize=7, zorder=3)
            ax.plot([values.mean()], [row], "s", markersize=8, zorder=4,
                    markerfacecolor="none", markeredgecolor=PALETTE[3], markeredgewidth=2.0)
        ax.axvline(1.0, color="#333333", linestyle="--", linewidth=1.1)
        ax.set_yticks(y)
        ax.set_yticklabels(order, fontsize=9.5)
        ax.set_ylim(-0.8, len(order) - 0.2)
        _log_x(ax, [0.5, 1, 2, 5, 10, 30])
        ax.set_xlim(0.4, 45)
        ax.set_xlabel("MASE per series (log axis, lower is better)")
        ax.grid(axis="y", visible=False)
    axes[0].text(1.06, 0.02, "MASE 1", transform=axes[0].get_xaxis_transform(),
                 fontsize=9, color="#333333", ha="left", va="bottom")
    titled(axes[0], "Every Hourly average sits above its own median",
           "414 series; thin line p10 to p90, thick part p25 to p75, dot the median, "
           "square the mean the tables report")
    titled(axes[1], "Weekly is skewed the same way",
           "359 series; MASE 1 is as accurate on the holdout as seasonal naive was in sample")
    figure.tight_layout()
    figure.savefig(out)
    plt.close(figure)
    return out


def interval_gain(out: Path) -> Path:
    """What switching from analytic to empirical intervals buys, per method."""
    labels, deltas, notes = [], [], []
    for frequency in FREQUENCIES:
        analytic, empirical = _paired(frequency)
        for label in analytic.index:
            labels.append(f"{frequency}   {label}")
            deltas.append(empirical.loc[label, "MSIS"] - analytic.loc[label, "MSIS"])
            notes.append(f"coverage {analytic.loc[label, 'coverage']:.1f}% to "
                         f"{empirical.loc[label, 'coverage']:.1f}%")

    figure, ax = plt.subplots(figsize=(11, 4.6))
    y = np.arange(len(labels))[::-1]
    ax.barh(y, deltas, height=0.6, color=EMPIRICAL)
    for row, note in zip(y, notes, strict=True):
        ax.annotate(note, (0, row), xytext=(8, 0), fontsize=9, textcoords="offset points",
                    ha="left", va="center", color="#5a5a5a")
    ax.axvline(0, color="#333333", lw=1.1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.set_ylim(-0.7, len(labels) - 0.3)
    ax.set_xlim(-64, 24)
    ax.set_xlabel("change in MSIS when the interval comes from residuals instead of the model")
    ax.grid(axis="y", visible=False)
    titled(ax, "The residual interval wins on MSIS even where it covers less",
           "MSIS charges for width as well as for misses; all six got narrower, and five "
           "of them gave up coverage to do it")
    figure.tight_layout()
    figure.savefig(out)
    plt.close(figure)
    return out


def _running(frequency: str, interval: str) -> np.ndarray:
    """Coverage of seasonal_naive averaged over the first k series, for every k."""
    raw = pd.read_csv(REPORTS / f"raw_{frequency}.csv")
    rows = raw[(raw.method == "seasonal_naive") & (raw.interval == interval)]
    return rows.sort_values("series").cover95.expanding().mean().to_numpy() * 100


def _shrink(path: Path) -> None:
    """Rewrite every frame onto one shared palette, which roughly halves the file."""
    src = Image.open(path)
    frames, durations = [], []
    try:
        while True:
            frames.append(src.convert("RGB"))
            durations.append(src.info.get("duration", 62))
            src.seek(src.tell() + 1)
    except EOFError:
        pass
    shared = frames[len(frames) // 2].quantize(64, method=Image.Quantize.MEDIANCUT)
    quantised = [f.quantize(palette=shared, dither=Image.Dither.NONE) for f in frames]
    quantised[0].save(path, save_all=True, append_images=quantised[1:], loop=0,
                      duration=durations, optimize=True)


def anim_coverage(out: Path, frames: int = 84, hold: int = 16, fps: int = 14,
                  start: int = 10) -> Path:
    """The published coverage numbers, built up one series at a time.

    Every frame is a mean of committed per-series measurements, so the GIF is
    identical on every run and each line ends on the number in the tables.
    """
    curves = {(f, i): _running(f, i) for f in FREQUENCIES for i in ("analytic", "empirical")}
    longest = max(len(c) for c in curves.values())

    figure, ax = plt.subplots(figsize=(7.8, 4.5))
    ax.set_xlim(start, longest * 1.14)
    ax.set_ylim(78, 102)
    ax.set_xlabel("number of series averaged, in the order M4 lists them")
    ax.set_ylabel("realised coverage of a nominal 95% interval (%)")
    titled(ax, "The Hourly coverage depends on how far down the file you read",
           "seasonal_naive; the forecasts and the holdout never change")
    ax.axhline(NOMINAL, color="#333333", linestyle="--", linewidth=1.2, zorder=2)
    ax.text(longest * 1.13, NOMINAL + 0.3, "nominal 95%", fontsize=9, color="#333333",
            ha="right", va="bottom")

    styles = {"Hourly": "-", "Weekly": (0, (5, 2))}
    colours = {"analytic": ANALYTIC, "empirical": EMPIRICAL}
    art, ends = {}, {}
    for key, curve in curves.items():
        frequency, interval = key
        art[key] = ax.plot([], [], color=colours[interval], linestyle=styles[frequency],
                           linewidth=2.0, zorder=3)[0]
        art[key + ("head",)] = ax.plot([], [], "o", color=colours[interval], markersize=6,
                                       zorder=4)[0]
        # A pair ends 1.4 points apart on Hourly, so the two readouts are pushed
        # to opposite sides of their own line.
        above = interval == "empirical"
        ends[key] = ax.text(len(curve) + longest * 0.015, curve[-1], "", fontsize=9,
                            color=colours[interval], ha="left",
                            va="bottom" if above else "top")
    art["readout"] = ax.text(0.015, 0.04, "", transform=ax.transAxes, fontsize=9.5,
                             color="#555555", ha="left", va="bottom")

    handles = [Line2D([], [], color=colours[i], linestyle=styles[f], linewidth=2.0,
                      label=f"{f}, {i}")
               for f in FREQUENCIES for i in ("analytic", "empirical")]
    ax.legend(handles=handles, loc="upper right", ncol=2)

    cuts = np.linspace(start, longest, frames).astype(int)

    def draw(i):
        cut = cuts[min(i, frames - 1)]
        for key, curve in curves.items():
            k = min(cut, len(curve))
            art[key].set_data(np.arange(1, k + 1), curve[:k])
            art[key + ("head",)].set_data([k], [curve[k - 1]])
            if i >= frames:
                ends[key].set_text(f"{curve[-1]:.1f}")
        art["readout"].set_text(f"first {cut} series")
        return list(art.values()) + list(ends.values())

    figure.tight_layout()
    animation = FuncAnimation(figure, draw, frames=frames + hold, interval=1000 // fps,
                              blit=False)
    animation.save(out, writer=PillowWriter(fps=fps), dpi=100)
    plt.close(figure)
    _shrink(out)
    return out


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in (
        coverage(FIGURES / "coverage.png"),
        coverage_width(FIGURES / "coverage-width.png"),
        point_vs_interval(FIGURES / "point-vs-interval.png"),
        spread(FIGURES / "per-series.png"),
        interval_gain(FIGURES / "interval-gain.png"),
        anim_coverage(FIGURES / "coverage-by-series.gif"),
    ):
        print(f"-> {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
