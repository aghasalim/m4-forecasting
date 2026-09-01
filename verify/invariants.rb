# Invariants the design of the backtest guarantees, checked against the files
# it actually wrote.
#
# Some of the README's claims are not arithmetic, they are structural, and no
# recomputation of a mean would notice if they broke:
#
#   "Same point forecast, two ways of putting an interval around it" only holds
#   if the analytic and empirical rows of a series carry identical sMAPE, MASE
#   and OWA. If the empirical path ever changed the point forecast, the
#   comparison in section 1 would be between two different forecasters and the
#   whole argument would be about the wrong thing.
#
#   "naive, naive2 and seasonal_naive are the same forecast on Weekly" is stated
#   in the limitations to explain why that table looks degenerate. It is
#   checkable: those rows should be identical on Weekly and must not be on
#   Hourly, or the seasonal period is not doing what the code says.
#
#   OWA is defined against Naive2, so Naive2's own OWA is 1 by construction. A
#   value that is 1.0000001 would mean the baseline used for the ratio is not
#   the baseline reported in the table.
#
# Coverage is also checked to be a whole number of hits out of the horizon,
# which pins the horizon at M4's 48 and 13 from the numbers themselves.

require "csv"
require "set"

root = ARGV[0] || "."
SPEC = { "Hourly" => 48, "Weekly" => 13 }.freeze
METHODS = %w[naive naive2 seasonal_naive theta].freeze
INTERVALS = %w[analytic empirical].freeze
POINT = %w[smape mase owa].freeze
METRICS = %w[smape mase cover95 width msis owa].freeze

bad = 0

def problem(msg)
  puts "  #{msg}"
end

SPEC.each do |freq, horizon|
  rows = CSV.read(File.join(root, "reports", "raw_#{freq}.csv"), headers: true)
  by_series = Hash.new { |h, k| h[k] = {} }
  rows.each do |r|
    key = [r["method"], r["interval"]]
    if by_series[r["series"].to_i].key?(key)
      problem("#{freq}: series #{r['series']} has two #{key.join('/')} rows")
      bad += 1
    end
    by_series[r["series"].to_i][key] = r
  end

  ids = by_series.keys.sort
  puts "#{freq}: #{rows.size} rows, #{ids.size} series"
  if ids != (0...ids.size).to_a
    problem("series ids are not 0..#{ids.size - 1} without gaps")
    bad += 1
  end

  want = METHODS.product(INTERVALS).to_set
  incomplete = ids.count { |i| by_series[i].keys.to_set != want }
  if incomplete > 0
    problem("#{incomplete} series do not have all #{want.size} method/interval rows")
    bad += 1
  else
    puts "  every series has all #{want.size} method and interval rows"
  end

  # The interval construction must not touch the point forecast.
  moved = 0
  ids.each do |i|
    METHODS.each do |m|
      a = by_series[i][[m, "analytic"]]
      e = by_series[i][[m, "empirical"]]
      next if a.nil? || e.nil?
      moved += 1 if POINT.any? { |c| a[c] != e[c] }
    end
  end
  if moved > 0
    problem("#{moved} method/series pairs have different point metrics under the two intervals")
    bad += 1
  else
    puts "  point metrics identical across both interval constructions, on all #{ids.size} series"
  end

  # OWA is a ratio to Naive2, so Naive2's own OWA is 1 by definition.
  off = ids.count { |i| INTERVALS.any? { |iv| by_series[i][["naive2", iv]]["owa"].to_f != 1.0 } }
  if off > 0
    problem("#{off} series have a naive2 OWA that is not exactly 1")
    bad += 1
  else
    puts "  naive2 OWA is exactly 1 on every series, as its definition requires"
  end

  # Coverage is hits out of the horizon, so it lands on a grid of 1/h.
  offgrid = rows.count do |r|
    k = r["cover95"].to_f * horizon
    (k - k.round).abs > 1e-9
  end
  if offgrid > 0
    problem("#{offgrid} coverage values are not a whole number of hits out of #{horizon}")
    bad += 1
  else
    puts "  every coverage is k/#{horizon}, which is the horizon M4 sets for #{freq}"
  end

  # Weekly has m = 1, so three of the four methods are the same forecaster.
  same = ids.all? do |i|
    INTERVALS.all? do |iv|
      base = by_series[i][["naive", iv]]
      %w[naive2 seasonal_naive].all? { |m| METRICS.all? { |c| by_series[i][[m, iv]][c] == base[c] } }
    end
  end
  if freq == "Weekly"
    if same
      puts "  naive, naive2 and seasonal_naive are byte identical, as m=1 requires"
    else
      problem("Weekly: the three m=1 methods are not identical, which the README says they are")
      bad += 1
    end
  else
    if same
      problem("Hourly: the three methods are identical, so the seasonal period is not being used")
      bad += 1
    else
      puts "  the three methods differ, so m=24 is doing something on Hourly"
    end
  end
end

if bad > 0
  puts "\n#{bad} invariants broken"
  exit 1
end
puts "\nevery structural invariant the backtest promises holds in the files it wrote"
