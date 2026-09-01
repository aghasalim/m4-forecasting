/* The two metric kernels behind every number in the README, in C.
 *
 * Kernel one, always run: OWA. Every OWA in reports/raw_*.csv is a ratio to a
 * Naive2 baseline computed on the same series, so it is not an independent
 * column, it is a function of the sMAPE and MASE columns sitting next to it.
 * Nothing checked that relationship. This rebuilds every OWA in both raw files
 * from the naive2 rows of the same series and requires agreement.
 *
 * Kernel two, run only when the M4 CSVs are present under data/: the MASE
 * scaling denominator. MASE divides by the mean in sample seasonal naive error,
 * which is the part of the metric that makes it comparable across series and
 * the part nothing else here recomputes. This reads the raw competition data,
 * builds the seasonal naive forecast for the 48 hour holdout, and reproduces
 * the per series sMAPE and MASE that reports/raw_Hourly.csv publishes. data/ is
 * not tracked (six megabytes of public CSV, refetched by `make data`), so this
 * kernel says it is skipped rather than failing when the files are absent.
 *
 * Columns are resolved by name, so a column added upstream cannot silently
 * shift what is read.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LINE 32768
#define MAX_SERIES 2000
#define OWA_TOL 1e-12
#define DATA_TOL 1e-9
#define M_HOURLY 24
#define H_HOURLY 48

static char line[LINE];
static char header[LINE];

/* Index of a named column in a CSV header, or -1. */
static int column_of(const char *head, const char *name)
{
    char buf[LINE];
    strncpy(buf, head, sizeof buf - 1);
    buf[sizeof buf - 1] = '\0';

    int i = 0;
    for (char *tok = strtok(buf, ",\r\n"); tok; tok = strtok(NULL, ",\r\n"), i++) {
        char *s = tok;
        if (*s == '"') s++;
        char *q = strchr(s, '"');
        if (q) *q = '\0';
        if (strcmp(s, name) == 0)
            return i;
    }
    return -1;
}

/* Field `index` of a CSV line, quotes and trailing newline removed. */
static const char *field(const char *src, int index)
{
    static char out[256];
    int col = 0;
    const char *p = src;
    while (col < index) {
        p = strchr(p, ',');
        if (!p)
            return "";
        p++;
        col++;
    }
    const char *end = strchr(p, ',');
    size_t n = end ? (size_t)(end - p) : strlen(p);
    if (n >= sizeof out)
        n = sizeof out - 1;
    memcpy(out, p, n);
    out[n] = '\0';
    char *nl = strpbrk(out, "\r\n");
    if (nl) *nl = '\0';
    if (out[0] == '"') {
        memmove(out, out + 1, strlen(out));
        char *q = strchr(out, '"');
        if (q) *q = '\0';
    }
    return out;
}

/* ---- kernel one: OWA from the sMAPE and MASE of the same series ---------- */

struct base { double smape, mase; int seen; };

static int check_owa(const char *root, const char *freq, double *worst_out, long *rows_out)
{
    char path[1024];
    snprintf(path, sizeof path, "%s/reports/raw_%s.csv", root, freq);
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return -1; }
    if (!fgets(header, sizeof header, f)) { fclose(f); return -1; }

    const int c_series = column_of(header, "series");
    const int c_method = column_of(header, "method");
    const int c_smape  = column_of(header, "smape");
    const int c_mase   = column_of(header, "mase");
    const int c_owa    = column_of(header, "owa");
    const int c_iv     = column_of(header, "interval");
    if (c_series < 0 || c_method < 0 || c_smape < 0 || c_mase < 0 || c_owa < 0 || c_iv < 0) {
        fprintf(stderr, "raw_%s.csv is missing a column this needs\n", freq);
        fclose(f);
        return -1;
    }

    static struct base bases[MAX_SERIES];
    memset(bases, 0, sizeof bases);
    long rows = 0;

    /* pass one: the Naive2 baseline of each series */
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '\n' || line[0] == '\0') continue;
        rows++;
        if (strcmp(field(line, c_method), "naive2") != 0) continue;
        if (strcmp(field(line, c_iv), "analytic") != 0) continue;
        const int s = atoi(field(line, c_series));
        if (s < 0 || s >= MAX_SERIES) { fprintf(stderr, "series id %d out of range\n", s); fclose(f); return -1; }
        bases[s].smape = atof(field(line, c_smape));
        bases[s].mase  = atof(field(line, c_mase));
        bases[s].seen  = 1;
    }

    /* pass two: rebuild every OWA from those baselines */
    rewind(f);
    if (!fgets(header, sizeof header, f)) { fclose(f); return -1; }
    double worst = 0.0;
    long checked = 0;
    int bad = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '\n' || line[0] == '\0') continue;
        const int s = atoi(field(line, c_series));
        if (s < 0 || s >= MAX_SERIES || !bases[s].seen) {
            fprintf(stderr, "series %d has no naive2 baseline row\n", s);
            bad++;
            continue;
        }
        const double smape = atof(field(line, c_smape));
        const double mase  = atof(field(line, c_mase));
        const double want  = atof(field(line, c_owa));
        const double got = 0.5 * (smape / bases[s].smape + mase / bases[s].mase);
        const double d = fabs(got - want);
        if (!(d <= OWA_TOL)) {
            if (bad < 5)
                printf("    series %d %s: OWA %.15f recomputed %.15f\n",
                       s, field(line, c_method), want, got);
            bad++;
        }
        if (d > worst) worst = d;
        checked++;
    }
    fclose(f);

    *worst_out = worst;
    *rows_out = checked;
    if (rows != checked) {
        fprintf(stderr, "read %ld rows but checked %ld\n", rows, checked);
        return -1;
    }
    return bad;
}

/* ---- kernel two: the seasonal naive scaling denominator ------------------ */

/* Reads one M4 wide CSV: first field is the series name, the rest are values,
 * shorter series padded with empty fields. Returns the number of series. */
static int read_m4(const char *path, double **rows, int *lengths, int max_rows)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    if (!fgets(line, sizeof line, f)) { fclose(f); return -1; }

    int n = 0;
    while (fgets(line, sizeof line, f) && n < max_rows) {
        if (line[0] == '\n' || line[0] == '\0') continue;
        int cap = 64, len = 0;
        double *v = malloc((size_t)cap * sizeof *v);
        if (!v) { fclose(f); return -1; }
        int first = 1;
        /* plain strtok: nothing else tokenises while this loop runs, and
         * strtok_r is not visible under -std=c99 on glibc */
        for (char *tok = strtok(line, ",\r\n"); tok; tok = strtok(NULL, ",\r\n")) {
            if (first) { first = 0; continue; }  /* the series id */
            char *s = tok;
            if (*s == '"') s++;
            char *q = strchr(s, '"');
            if (q) *q = '\0';
            if (*s == '\0') continue;
            if (len == cap) {
                cap *= 2;
                double *bigger = realloc(v, (size_t)cap * sizeof *v);
                if (!bigger) { free(v); fclose(f); return -1; }
                v = bigger;
            }
            v[len++] = atof(s);
        }
        rows[n] = v;
        lengths[n] = len;
        n++;
    }
    fclose(f);
    return n;
}

static int check_from_data(const char *root)
{
    char train[1024], test[1024], pubpath[1024];
    snprintf(train, sizeof train, "%s/data/Hourly-train.csv", root);
    snprintf(test, sizeof test, "%s/data/Hourly-test.csv", root);
    snprintf(pubpath, sizeof pubpath, "%s/reports/raw_Hourly.csv", root);

    FILE *probe = fopen(train, "r");
    if (!probe) {
        printf("  seasonal naive kernel: skipped, no data/Hourly-train.csv "
               "(6 MB of public M4 CSV, fetched by `make data`)\n");
        return 0;
    }
    fclose(probe);

    static double *tr[MAX_SERIES], *te[MAX_SERIES];
    static int trn[MAX_SERIES], ten[MAX_SERIES];
    const int n_tr = read_m4(train, tr, trn, MAX_SERIES);
    const int n_te = read_m4(test, te, ten, MAX_SERIES);
    if (n_tr <= 0 || n_te != n_tr) {
        fprintf(stderr, "  train/test row counts disagree: %d and %d\n", n_tr, n_te);
        return 1;
    }

    /* published per series numbers for seasonal_naive */
    static double p_smape[MAX_SERIES], p_mase[MAX_SERIES];
    static int p_seen[MAX_SERIES];
    memset(p_seen, 0, sizeof p_seen);

    FILE *f = fopen(pubpath, "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", pubpath); return 1; }
    if (!fgets(header, sizeof header, f)) { fclose(f); return 1; }
    const int c_series = column_of(header, "series");
    const int c_method = column_of(header, "method");
    const int c_smape = column_of(header, "smape");
    const int c_mase = column_of(header, "mase");
    const int c_iv = column_of(header, "interval");
    while (fgets(line, sizeof line, f)) {
        if (strcmp(field(line, c_method), "seasonal_naive") != 0) continue;
        if (strcmp(field(line, c_iv), "analytic") != 0) continue;
        const int s = atoi(field(line, c_series));
        if (s < 0 || s >= MAX_SERIES) continue;
        p_smape[s] = atof(field(line, c_smape));
        p_mase[s] = atof(field(line, c_mase));
        p_seen[s] = 1;
    }
    fclose(f);

    double worst_s = 0.0, worst_m = 0.0;
    int checked = 0, bad = 0;
    for (int i = 0; i < n_tr; i++) {
        if (!p_seen[i]) continue;
        const double *y = tr[i];
        const int ny = trn[i];
        if (ny <= M_HOURLY || ten[i] < H_HOURLY) continue;

        /* seasonal naive: repeat the last full season across the horizon */
        double sum_abs = 0.0, sum_smape = 0.0;
        for (int k = 0; k < H_HOURLY; k++) {
            const double pt = y[ny - M_HOURLY + (k % M_HOURLY)];
            const double a = te[i][k];
            sum_abs += fabs(a - pt);
            const double denom = fabs(a) + fabs(pt);
            sum_smape += denom == 0.0 ? 0.0 : 2.0 * fabs(a - pt) / denom;
        }
        /* the MASE denominator: mean in sample seasonal naive error */
        double scale = 0.0;
        for (int t = M_HOURLY; t < ny; t++)
            scale += fabs(y[t] - y[t - M_HOURLY]);
        scale /= (double)(ny - M_HOURLY);
        if (scale == 0.0 || !isfinite(scale)) scale = 1.0;

        const double smape = 100.0 * sum_smape / H_HOURLY;
        const double mase = (sum_abs / H_HOURLY) / scale;
        const double ds = fabs(smape - p_smape[i]);
        const double dm = fabs(mase - p_mase[i]);
        if (ds > worst_s) worst_s = ds;
        if (dm > worst_m) worst_m = dm;
        if (!(ds <= DATA_TOL) || !(dm <= DATA_TOL)) {
            if (bad < 5)
                printf("    series %d: sMAPE %.10f vs %.10f, MASE %.10f vs %.10f\n",
                       i, smape, p_smape[i], mase, p_mase[i]);
            bad++;
        }
        checked++;
    }
    for (int i = 0; i < n_tr; i++) { free(tr[i]); free(te[i]); }

    printf("  seasonal naive kernel: %d series from data/Hourly-{train,test}.csv, "
           "worst |d| sMAPE %.1e MASE %.1e  %s\n",
           checked, worst_s, worst_m, bad ? "FAIL" : "ok");
    if (checked == 0) {
        fprintf(stderr, "  no series checked against the M4 data\n");
        return 1;
    }
    return bad ? 1 : 0;
}

int main(int argc, char **argv)
{
    const char *root = argc > 1 ? argv[1] : ".";
    int failures = 0;

    printf("OWA rebuilt from the sMAPE and MASE of the same series\n");
    const char *freqs[2] = { "Hourly", "Weekly" };
    for (int i = 0; i < 2; i++) {
        double worst = 0.0;
        long rows = 0;
        const int bad = check_owa(root, freqs[i], &worst, &rows);
        if (bad < 0) return 2;
        printf("  %-6s %ld rows, worst |d| %.1e  %s\n",
               freqs[i], rows, worst, bad ? "FAIL" : "ok");
        failures += bad;
    }

    printf("\nMASE scaling denominator, from the M4 data itself\n");
    failures += check_from_data(root);

    if (failures) {
        printf("\n%d disagreements\n", failures);
        return 1;
    }
    printf("\nC agrees with the published per series metrics\n");
    return 0;
}
