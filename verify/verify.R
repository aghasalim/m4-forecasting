# Is the README's headline claim a real effect or a point estimate with no
# error bar?
#
# The repository states that nothing reaches its nominal 95% coverage on Hourly,
# that the Weekly analytic interval by contrast is "essentially nominal" at
# 94.9%, and that the empirical interval beats the analytic one on MSIS in every
# case. All three are read off means over a few hundred series, with no interval
# on any of them, so none of them had been separated from sampling noise.
#
# This resamples the series in base R, with R's own generator, and asks:
#
#   under-coverage   is the upper end of a 95% bootstrap interval on each
#                    Hourly coverage still below the nominal 0.95
#   calibration      does the Weekly analytic interval, the one the README
#                    calls honest, contain 0.95
#   MSIS             does the analytic interval lose to the empirical one on
#                    more series than chance would give, by a sign test
#
# The series is the resampling unit because it is the independent one: the 48
# hours within a series are one forecast, not 48.
#
# No packages, so CI needs nothing beyond base R.

args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args) > 0) args[1] else "."
set.seed(20260901)

DRAWS <- 4000
NOMINAL <- 0.95
MEAN_TOL <- 5.1e-5   # the published summaries are rounded to four decimals
failures <- 0

boot_ci <- function(x, idx) {
    means <- rowMeans(matrix(x[idx], nrow = nrow(idx)))
    quantile(means, c(0.025, 0.975), names = FALSE)
}

for (freq in c("Hourly", "Weekly")) {
    raw <- read.csv(file.path(root, "reports", sprintf("raw_%s.csv", freq)))
    pub <- read.csv(file.path(root, "reports", sprintf("summary_%s.csv", freq)))
    series <- sort(unique(raw$series))
    n <- length(series)

    # One resampling of the series, shared by every row, so the comparisons
    # between rows below are paired rather than independently noisy.
    idx <- matrix(sample.int(n, n * DRAWS, replace = TRUE), nrow = DRAWS)

    cat(sprintf("\n%s: %d series, %d bootstrap draws over series\n", freq, n, DRAWS))
    for (i in seq_len(nrow(pub))) {
        m <- pub$method[i]
        iv <- pub$interval[i]
        sub <- raw[raw$method == m & raw$interval == iv, ]
        sub <- sub[order(sub$series), ]
        if (nrow(sub) != n) {
            cat(sprintf("  %s/%s has %d rows, expected %d\n", m, iv, nrow(sub), n))
            failures <- failures + 1
            next
        }

        got <- mean(sub$cover95)
        d <- abs(got - pub$coverage95[i])
        if (d > MEAN_TOL) {
            cat(sprintf("  %s/%s mean coverage %.6f, published %.4f\n", m, iv, got, pub$coverage95[i]))
            failures <- failures + 1
        }

        ci <- boot_ci(sub$cover95, idx)
        below <- ci[2] < NOMINAL
        contains <- ci[1] <= NOMINAL && ci[2] >= NOMINAL

        # The Hourly claim is that none of these reaches nominal. The Weekly
        # claim is narrower: the three analytic rows at 94.9% are the ones
        # called calibrated, and they should contain 0.95.
        if (freq == "Hourly") {
            ok <- below
            verdict <- "under 0.95"
        } else if (iv == "analytic" && round(got, 4) == 0.9494) {
            ok <- contains
            verdict <- "contains 0.95"
        } else {
            ok <- TRUE
            verdict <- if (below) "under 0.95" else "contains 0.95"
        }
        failures <- failures + !ok
        cat(sprintf("  %-14s %-9s coverage %.4f  95%% CI [%.4f, %.4f]  %-13s %s\n",
                    m, iv, got, ci[1], ci[2], verdict, if (ok) "ok" else "FAIL"))
    }

    # Paired, per series: does the analytic interval really lose on MSIS?
    cat(sprintf("  sign test on MSIS, analytic against empirical, %d series each\n", n))
    for (m in unique(raw$method)) {
        a <- raw[raw$method == m & raw$interval == "analytic", ]
        e <- raw[raw$method == m & raw$interval == "empirical", ]
        a <- a[order(a$series), ]
        e <- e[order(e$series), ]
        worse <- sum(a$msis > e$msis)
        p <- binom.test(worse, n, 0.5, alternative = "greater")$p.value
        ok <- p < 1e-3
        failures <- failures + !ok
        cat(sprintf("    %-14s analytic worse on %3d of %3d series  p %.2e  %s\n",
                    m, worse, n, p, if (ok) "ok" else "FAIL"))
    }
}

# The ranking claim: seasonal_naive beats the Naive2 baseline outright on
# Hourly, which means its OWA interval must sit entirely below 1.
raw <- read.csv(file.path(root, "reports", "raw_Hourly.csv"))
sub <- raw[raw$method == "seasonal_naive" & raw$interval == "analytic", ]
n <- nrow(sub)
idx <- matrix(sample.int(n, n * DRAWS, replace = TRUE), nrow = DRAWS)
ci <- boot_ci(sub$owa, idx)
ok <- ci[2] < 1
failures <- failures + !ok
cat(sprintf("\nHourly seasonal_naive OWA %.4f  95%% CI [%.4f, %.4f]  below 1  %s\n",
            mean(sub$owa), ci[1], ci[2], if (ok) "ok" else "FAIL"))

if (failures > 0) {
    cat(sprintf("\n%d checks failed\n", failures))
    quit(status = 1)
}
cat("\nthe under-coverage, the calibrated Weekly interval and the MSIS gap all\n")
cat("survive resampling the series, so they are not artefacts of the mean\n")
