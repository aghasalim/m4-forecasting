//! Two questions about the published numbers that the Python never asked.
//!
//! 1. Does the ranking depend on particular series? The README says
//!    `seasonal_naive` "wins outright" on Hourly, that its empirical interval is
//!    the best MSIS on the board, and that theta comes out worse than the Naive2
//!    baseline on both frequencies. Those are read off means over 414 and 359
//!    series. This deletes every series in turn, all 773 of them, recomputes all
//!    eight group means each time, and checks the ordering never changes. It is
//!    the exhaustive version of "is this robust", which is cheap here and was
//!    never run.
//!
//! 2. Is the bootstrap in verify/verify.R big enough to support its own
//!    conclusion? R draws 4000 resamples and concludes that the upper end of
//!    every Hourly coverage interval sits below the nominal 0.95. For the naive
//!    analytic row that margin is small. A 4000 draw interval endpoint is itself
//!    a Monte Carlo estimate with its own scatter, so this runs a 100,000 draw
//!    reference and 30 independent 4000 draw replicates, measures the scatter of
//!    the endpoint, and requires the margin to be several times that scatter.
//!    Without this, "the interval stops below 0.95" could be a fact about the
//!    seed.

use std::env;
use std::fs;
use std::process::exit;

const REFERENCE_DRAWS: usize = 100_000;
const R_DRAWS: usize = 4_000;
const REPLICATES: usize = 30;
const NOMINAL: f64 = 0.95;
const SIGMA: f64 = 4.0;

/// xorshift64*. Not cryptographic and not meant to be: it needs to be uniform,
/// fast and seeded reproducibly, so a failure can be re-run.
struct Rng(u64);

impl Rng {
    fn new(seed: u64) -> Self {
        Rng(seed | 1)
    }
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    fn below(&mut self, n: usize) -> usize {
        (self.next_u64() % n as u64) as usize
    }
}

struct Group {
    method: String,
    interval: String,
    owa: Vec<f64>,
    msis: Vec<f64>,
    cover: Vec<f64>,
}

impl Group {
    fn name(&self) -> String {
        format!("{}/{}", self.method, self.interval)
    }
}

fn load(root: &str, freq: &str) -> (usize, Vec<Group>) {
    let path = format!("{}/reports/raw_{}.csv", root, freq);
    let text = fs::read_to_string(&path).unwrap_or_else(|e| {
        eprintln!("cannot read {}: {}", path, e);
        exit(2)
    });

    let mut lines = text.lines();
    let header: Vec<&str> = lines.next().expect("empty file").trim().split(',').collect();
    let col = |name: &str| {
        header.iter().position(|h| *h == name).unwrap_or_else(|| {
            eprintln!("raw_{}.csv has no {} column", freq, name);
            exit(2)
        })
    };
    let (c_series, c_method, c_iv) = (col("series"), col("method"), col("interval"));
    let (c_owa, c_msis, c_cover) = (col("owa"), col("msis"), col("cover95"));

    let mut groups: Vec<Group> = Vec::new();
    let mut n_series = 0usize;
    for line in lines.filter(|l| !l.trim().is_empty()) {
        let f: Vec<&str> = line.trim().split(',').collect();
        let s: usize = f[c_series].parse().expect("series id is not an integer");
        n_series = n_series.max(s + 1);
        let (method, iv) = (f[c_method], f[c_iv]);
        let g = match groups
            .iter()
            .position(|g| g.method == method && g.interval == iv)
        {
            Some(i) => &mut groups[i],
            None => {
                groups.push(Group {
                    method: method.to_string(),
                    interval: iv.to_string(),
                    owa: Vec::new(),
                    msis: Vec::new(),
                    cover: Vec::new(),
                });
                groups.last_mut().unwrap()
            }
        };
        g.owa.push(f[c_owa].parse().expect("owa is not a number"));
        g.msis.push(f[c_msis].parse().expect("msis is not a number"));
        g.cover.push(f[c_cover].parse().expect("cover95 is not a number"));
    }

    for g in &groups {
        if g.owa.len() != n_series {
            eprintln!("{} has {} rows, expected {}", g.name(), g.owa.len(), n_series);
            exit(2);
        }
    }
    groups.sort_by(|a, b| a.name().cmp(&b.name()));
    (n_series, groups)
}

/// Leave-one-out means of every group, as a matrix indexed [group][series].
fn jackknife(groups: &[Group], pick: impl Fn(&Group) -> &Vec<f64>, n: usize) -> Vec<Vec<f64>> {
    groups
        .iter()
        .map(|g| {
            let v = pick(g);
            let total: f64 = v.iter().sum();
            v.iter().map(|x| (total - x) / (n - 1) as f64).collect()
        })
        .collect()
}

fn argmin(values: &[f64]) -> usize {
    let mut best = 0;
    for (i, v) in values.iter().enumerate() {
        if *v < values[best] {
            best = i;
        }
    }
    best
}

/// Linear interpolation between order statistics: numpy's default and R's
/// type 7, which is what the Python and verify.R both use.
fn quantile(sorted: &[f64], q: f64) -> f64 {
    let pos = q * (sorted.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        sorted[lo]
    } else {
        sorted[lo] + (pos - lo as f64) * (sorted[hi] - sorted[lo])
    }
}

/// Bootstrap over series, resampling once per draw and reusing that resample
/// for every group, which is how verify.R does it.
fn bootstrap_upper(groups: &[Group], n: usize, draws: usize, seed: u64) -> Vec<f64> {
    let mut rng = Rng::new(seed);
    let mut stats: Vec<Vec<f64>> = vec![Vec::with_capacity(draws); groups.len()];
    let mut idx = vec![0usize; n];
    for _ in 0..draws {
        for slot in idx.iter_mut() {
            *slot = rng.below(n);
        }
        for (k, g) in groups.iter().enumerate() {
            let mut sum = 0.0;
            for &i in &idx {
                sum += g.cover[i];
            }
            stats[k].push(sum / n as f64);
        }
    }
    stats
        .iter_mut()
        .map(|s| {
            s.sort_by(|a, b| a.partial_cmp(b).unwrap());
            quantile(s, 0.975)
        })
        .collect()
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let root = args.get(1).map(String::as_str).unwrap_or(".");
    let mut failures = 0;

    // --- 1. every series deleted in turn -------------------------------
    for freq in ["Hourly", "Weekly"] {
        let (n, groups) = load(root, freq);
        println!("{}: {} series, {} method/interval groups", freq, n, groups.len());

        let owa = jackknife(&groups, |g| &g.owa, n);
        let msis = jackknife(&groups, |g| &g.msis, n);

        // OWA is a property of the point forecast, so the two interval rows of
        // a method carry the same value; rank the methods on the analytic rows.
        let point: Vec<usize> = (0..groups.len())
            .filter(|&k| groups[k].interval == "analytic")
            .collect();

        let mut owa_winners = std::collections::BTreeSet::new();
        let mut msis_winners = std::collections::BTreeSet::new();
        let mut theta_min = f64::MAX;
        let mut theta_max = f64::MIN;
        for j in 0..n {
            let col: Vec<f64> = point.iter().map(|&k| owa[k][j]).collect();
            owa_winners.insert(groups[point[argmin(&col)]].method.clone());

            let all: Vec<f64> = (0..groups.len()).map(|k| msis[k][j]).collect();
            msis_winners.insert(groups[argmin(&all)].name());

            for &k in &point {
                if groups[k].method == "theta" {
                    theta_min = theta_min.min(owa[k][j]);
                    theta_max = theta_max.max(owa[k][j]);
                }
            }
        }

        let expected_owa = if freq == "Hourly" { "seasonal_naive" } else { "naive" };
        let owa_ok = owa_winners.len() == 1 && owa_winners.contains(expected_owa);
        // On Weekly m = 1, so naive, naive2 and seasonal_naive are the same
        // forecaster and tie; the winner there is a tie the ordering picks
        // first, and only the Hourly claim is about a method beating others.
        let msis_expected = if freq == "Hourly" {
            "seasonal_naive/empirical"
        } else {
            "naive/empirical"
        };
        let msis_ok = msis_winners.len() == 1 && msis_winners.contains(msis_expected);
        let theta_ok = theta_min > 1.0;

        failures += !owa_ok as i32 + !msis_ok as i32 + !theta_ok as i32;
        println!(
            "  best OWA over all {} deletions: {:?}  {}",
            n,
            owa_winners,
            if owa_ok { "ok" } else { "FAIL" }
        );
        println!(
            "  best MSIS over all {} deletions: {:?}  {}",
            n,
            msis_winners,
            if msis_ok { "ok" } else { "FAIL" }
        );
        println!(
            "  theta OWA stays in [{:.4}, {:.4}], above the Naive2 baseline of 1  {}",
            theta_min,
            theta_max,
            if theta_ok { "ok" } else { "FAIL" }
        );
    }

    // --- 2. how much of R's interval endpoint is noise -----------------
    let (n, groups) = load(root, "Hourly");
    println!(
        "\nHourly coverage, upper end of the 95% bootstrap interval\n\
         reference {} draws, scatter from {} runs of {} draws (what verify.R uses)",
        REFERENCE_DRAWS, REPLICATES, R_DRAWS
    );
    let reference = bootstrap_upper(&groups, n, REFERENCE_DRAWS, 0x5EED_1234);
    let mut replicates: Vec<Vec<f64>> = Vec::with_capacity(REPLICATES);
    for r in 0..REPLICATES {
        replicates.push(bootstrap_upper(&groups, n, R_DRAWS, 0xC0FFEE + r as u64 * 104_729));
    }

    for (k, g) in groups.iter().enumerate() {
        let ends: Vec<f64> = replicates.iter().map(|r| r[k]).collect();
        let mean = ends.iter().sum::<f64>() / ends.len() as f64;
        let sd = (ends.iter().map(|x| (x - mean).powi(2)).sum::<f64>()
            / (ends.len() - 1) as f64)
            .sqrt();
        let margin = NOMINAL - reference[k];
        let sigmas = margin / sd.max(1e-12);
        let ok = margin > 0.0 && sigmas >= SIGMA;
        failures += !ok as i32;
        println!(
            "  {:<26} upper {:.4}  margin to 0.95 {:.4}  noise sd {:.5}  {:5.1} sd  {}",
            g.name(),
            reference[k],
            margin,
            sd,
            sigmas,
            if ok { "ok" } else { "FAIL" }
        );
    }

    if failures > 0 {
        println!("\n{} checks failed", failures);
        exit(1);
    }
    println!(
        "\nno single series changes the ranking, and every Hourly coverage interval\n\
         clears 0.95 by more than {} times the scatter of its own endpoint",
        SIGMA
    );
}
