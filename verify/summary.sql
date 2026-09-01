-- Recompute reports/summary_Hourly.csv and reports/summary_Weekly.csv from the
-- per series files they were aggregated from.
--
-- The published summaries come out of one pandas groupby in
-- src/fc/backtest.py:summarise. Every table in the README, and every figure,
-- reads that output, so an error in the aggregation would be invisible: the
-- figures would agree with the tables because they come from the same place.
-- This redoes the same 16 rows in SQLite, straight from reports/raw_*.csv.
--
-- The published values are rounded to four decimals, so the comparison allows
-- half a unit in the last of them and nothing more.
--
-- Run: sqlite3 -init verify/summary.sql :memory: ""

.mode csv
.headers off
.import --csv reports/raw_Hourly.csv raw_hourly
.import --csv reports/raw_Weekly.csv raw_weekly
.import --csv reports/summary_Hourly.csv pub_hourly
.import --csv reports/summary_Weekly.csv pub_weekly

CREATE TEMP VIEW raw AS
    SELECT 'Hourly' AS freq, * FROM raw_hourly
    UNION ALL
    SELECT 'Weekly' AS freq, * FROM raw_weekly;

CREATE TEMP VIEW pub AS
    SELECT 'Hourly' AS freq, * FROM pub_hourly
    UNION ALL
    SELECT 'Weekly' AS freq, * FROM pub_weekly;

-- One row per (frequency, method, interval), which is what summarise() emits.
CREATE TEMP VIEW recomputed AS
    SELECT freq,
           method,
           "interval"                        AS iv,
           AVG(CAST(smape   AS REAL))        AS smape,
           AVG(CAST(mase    AS REAL))        AS mase,
           AVG(CAST(owa     AS REAL))        AS owa,
           AVG(CAST(cover95 AS REAL))        AS cover,
           AVG(CAST(width   AS REAL))        AS width,
           AVG(CAST(msis    AS REAL))        AS msis,
           COUNT(DISTINCT series)            AS n,
           COUNT(*)                          AS rows_read
    FROM raw
    GROUP BY freq, method, "interval";

CREATE TEMP VIEW cmp AS
    SELECT r.freq, r.method, r.iv, r.rows_read, r.n,
           MAX(ABS(r.smape - CAST(p.sMAPE      AS REAL)),
               ABS(r.mase  - CAST(p.MASE       AS REAL)),
               ABS(r.owa   - CAST(p.OWA        AS REAL)),
               ABS(r.cover - CAST(p.coverage95 AS REAL)),
               ABS(r.width - CAST(p.width      AS REAL)),
               ABS(r.msis  - CAST(p.MSIS       AS REAL))) AS worst,
           ABS(r.n - CAST(p.n AS INTEGER))                AS n_off
    FROM recomputed r
    JOIN pub p
      ON p.freq = r.freq AND p.method = r.method AND p."interval" = r.iv;

.mode list
SELECT printf('  %-6s %-14s %-9s %4d rows  n=%d  worst |d| %.2e  %s',
              freq, method, iv, rows_read, n, worst,
              CASE WHEN worst > 5.1e-5 OR n_off > 0 THEN 'FAIL' ELSE 'ok' END)
FROM cmp
ORDER BY freq, iv, method;

SELECT printf('RESULT %d %d',
              (SELECT COUNT(*) FROM cmp),
              (SELECT COUNT(*) FROM cmp WHERE worst > 5.1e-5 OR n_off > 0));
