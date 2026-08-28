# Forecasting, the interval is the forecast, and mine were wrong

[![ci](https://github.com/aghasalim/m4-forecasting/actions/workflows/ci.yml/badge.svg)](https://github.com/aghasalim/m4-forecasting/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Forecasting on the [M4 competition](https://github.com/Mcompetitions/M4-methods)
benchmark, 414 Hourly and 359 Weekly series, scored on M4's own holdout so the
numbers are comparable to published work rather than to a split I invented.
Built by a third-year Applied Computer Science (AI) student.

Nobody staffs a warehouse against the mean. They staff against the upper bound.
So this project treats the **prediction interval** as the deliverable and point
accuracy as the easy part, because a nominal 95% interval that covers 85% of
the time is not slightly imperfect, it is wrong, and no sMAPE will ever say so.

---


---

## Abstract

M4 is scored on point accuracy, and the prediction interval is usually an
afterthought. This work reverses that emphasis: the same four baseline methods are
run on the Hourly and Weekly subsets under two interval constructions, and the
question is whether a nominal 95% interval contains the truth 95% of the time.

Mostly it does not. Weekly analytic intervals land on 94.9%, essentially nominal.
Everything on Hourly under-covers, worst case 79.1% against a nominal 95%, a
16-point shortfall on an interval a user would take at face value. Empirical
intervals under-cover on Weekly too, but buy their coverage far more cheaply:
analytic intervals on Hourly are up to five times wider and still cover less.

Point accuracy and interval quality also do not rank the methods the same way.
OWA and MSIS disagree, so a method chosen on the competition metric carries no
guarantee about the intervals it produces.

**Contributions.** (i) Coverage measured against nominal rather than assumed.
(ii) A width-versus-coverage comparison separating honest coverage from wide
intervals. (iii) Evidence that the point-forecast ranking and the interval ranking
differ. (iv) Per-series distributions behind every aggregate, so the spread is
visible before a two-decimal ranking is read as settled.

---

## 1. Three results

**1. Nothing achieves its nominal coverage on Hourly. The best is 86.6%.**

Every method here advertises a 95% interval. None delivers one:

| method | interval | coverage (nominal 95%) | width | MSIS |
|---|---|---|---|---|
| **seasonal_naive** | **empirical** | **86.6%** | **4.31** | **8.82** |
| seasonal_naive | analytic | 85.2% | 6.06 | 11.06 |
| naive | empirical | 82.8% | 4.87 | 12.10 |
| theta | analytic | 91.3% | 23.52 | 33.30 |
| naive2 | analytic | 90.2% | 23.52 | 33.19 |

Theta and naive2 look closest to nominal, at nearly **four times the width**.
That is the trap in reading coverage alone: any target is reachable by widening
until the interval is useless. MSIS charges for width, and on that they are the
two worst methods on the board.

**2. Measuring your errors beats trusting your model.** Same point forecast,
two ways of putting an interval around it. For`seasonal_naive`, empirical
residual quantiles give **better coverage (86.6% vs 85.2%) at 29% narrower
width**, and MSIS drops from 11.06 to 8.82. The model's analytic band assumes
Gaussian, correctly-specified residuals; both are false, in the same direction.

**3. The baseline nobody reports wins outright.** On Hourly,`seasonal_naive`
takes an **OWA of 0.843**: best point accuracy *and* best intervals. Theta, the
method that won M3, scores **1.013**: worse than the naive2 baseline it is
measured against. On Weekly it is worse still, at 1.288.

| Hourly | sMAPE | MASE | OWA |
|---|---|---|---|
| **seasonal_naive** | **13.91** | **1.19** | **0.843** |
| theta | 15.41 | 2.11 | 1.013 |
| naive2 (baseline) | 17.36 | 2.27 | 1.000 |
| naive | 43.00 | 11.61 | 5.118 |

---

![realised coverage against the nominal 95%](reports/figures/coverage.png)

![coverage building up one series at a time](reports/figures/coverage-by-series.gif)

*Coverage as more series are averaged in, on the same seasonal_naive
forecasts and the same M4 holdout. Each line ends on the coverage quoted in the
first table, well short of the nominal 95%.*

![what the coverage costs in width](reports/figures/coverage-width.png)

![point accuracy against interval quality](reports/figures/point-vs-interval.png)

![what empirical intervals buy over analytic](reports/figures/interval-gain.png)

![per-series MASE behind every aggregate](reports/figures/per-series.png)

Every number in the tables above is a mean over hundreds of series, and the last
figure is the spread behind them. The distributions overlap heavily, which is
worth seeing before reading a two-decimal ranking as settled.

## 2. The bug, which is the point of the tests

My first empirical intervals covered **44 to 49%** on a nominal 95%. The cause was
not subtle once seen: I estimated the 2.5% and 97.5% quantiles from **three**
backtest folds. A tail quantile of three numbers cannot reach past their minimum
and maximum, so the "95% interval" was really about a 50% one.

What makes it worth writing down is that it *passed every test I had*, because
every test I had asked whether the maths ran, not whether an interval covered
anything. The fix is a fold count derived from available history (up to 24) with
a floor of 12 before tail quantiles are trusted at all, below that it falls
back to a Gaussian scaling of the same residuals, which uses them without
pretending to resolve their tails.`tests/test_fc.py` now asserts end-to-end
coverage, which is the test that would have caught it.

---

## 3. Limitations

- **Weekly has no seasonality in M4's setup** (`m=1`), so`naive`,`naive2` and
`seasonal_naive` are the *same forecast* there and report identical numbers.
  That is correct behaviour, not a bug, and it is why the Weekly table looks
  degenerate.
- **I have not compared these against the published M4 leaderboard.** OWA here
  is computed against my own Naive2 implementation, which is the competition's
  definition but not necessarily identical to their code to the decimal. Ranking
  claims are internal to this repo.
- **Two frequencies, not six.** Hourly and Weekly are 773 of M4's 100,000
  series. Hourly is strongly seasonal and Weekly is not, which is a deliberate
  contrast, but Monthly and Quarterly dominate the real benchmark and are absent.
- **No ML models.** Only statistical baselines. The M4 finding that pure ML
  underperformed statistical methods is well known; testing it myself is the
  obvious next step and is not done here.

Notably, the Weekly analytic intervals *are* well calibrated (94.9% against 95%)
while the Hourly ones are not (85.2%). The same construction, honest on one
frequency and not the other, which is the argument for measuring coverage per
dataset rather than trusting a method's reputation.

## 4. Running it

```bash
make setup && make test
```

```bash
make data && make backtest
```

Data is fetched from the public
[M4-methods](https://github.com/Mcompetitions/M4-methods) repository. No
credentials, no API keys.

## 5. Licence

MIT. M4 data © the M4 competition organisers.

## References

The papers and sources this implementation follows. Each one is here because
the code uses the method, the dataset or the metric it describes.

- **Makridakis, Spiliotis, Assimakopoulos. The M4 Competition: 100,000 time series and 61 forecasting methods. International Journal of Forecasting 36, 2020.** the dataset, the Naive2 benchmark and the OWA metric.
- **Hyndman, Koehler. Another look at measures of forecast accuracy. International Journal of Forecasting 22, 2006.** MASE.
- **Assimakopoulos, Nikolopoulos. The theta model. International Journal of Forecasting 16, 2000.** the Theta method.
