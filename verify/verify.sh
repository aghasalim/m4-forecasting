#!/usr/bin/env bash
# Recompute the published numbers in every language here and require agreement.
#
# Every table and every figure in the README comes out of one pandas run in
# src/fc/backtest.py. If the aggregation there were wrong, nothing downstream
# would notice, because everything downstream reads the same output: the figures
# would agree with the tables because they are the same numbers. The tests check
# that the code runs, not that it is right.
#
# So the summary tables are rebuilt from the per series files, the per series
# numbers are rebuilt from the M4 data where the data is available, the README is
# checked against both, and the two statistical claims the argument rests on are
# re-derived by resampling. A mistake would have to be made identically in every
# implementation below to survive.
#
# Each is skipped with a clear message if its toolchain is absent, so a laptop
# with half of them installed still runs the rest. CI has all of them.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
[ -d "$HOME/.cargo/bin" ] && PATH="$HOME/.cargo/bin:$PATH"

pass=0 fail=0 skip=0

run () {
    local name="$1" tool="$2"; shift 2
    printf '\n=== %s ===\n' "$name"
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'skipped: %s is not installed\n' "$tool"
        skip=$((skip + 1)); return
    fi
    if "$@"; then
        pass=$((pass + 1))
    else
        printf -- '--- FAILED: %s\n' "$name"
        fail=$((fail + 1))
    fi
}

# The SQL has no exit status of its own, so it prints a RESULT line and this
# reads it: how many of the 16 published groups were compared, and how many
# disagree past the rounding in the published files.
check_sql () {
    local out result
    out=$(sqlite3 -init verify/summary.sql :memory: "" 2>/dev/null) || return 1
    echo "$out"
    result=$(echo "$out" | awk '/^RESULT/ {print $2, $3}')
    case "$result" in
        "16 0") echo "SQL rebuilds all 16 summary rows from the per series files"; return 0 ;;
        "")     echo "the SQL produced no RESULT line"; return 1 ;;
        *)      echo "SQL disagreement: checked/failed = $result"; return 1 ;;
    esac
}

check_c () {
    cc -std=c99 -O2 -Wall -Wextra -Wpedantic -Werror \
       -o "${TMPDIR:-/tmp}/m4metrics" verify/metrics.c -lm || return 1
    "${TMPDIR:-/tmp}/m4metrics" "$root"
}

check_go () { ( cd verify/gocheck && go run . -root "$root" ); }

check_rust () { ( cd verify/stability && cargo run --release --quiet -- "$root" ); }

run "SQL, the summary tables"        sqlite3 check_sql
run "C, the metric kernels"          cc      check_c
run "Go, files and README tables"    go      check_go
run "R, the statistical claims"      Rscript Rscript verify/verify.R "$root"
run "Rust, stability and MC noise"   cargo   check_rust
run "JavaScript, summary.json"       node    node verify/summary.js "$root"
run "Ruby, structural invariants"    ruby    ruby verify/invariants.rb "$root"
run "Java, the claims in the prose"  java    java verify/Claims.java "$root"

printf '\n%s\n' "----------------------------------------"
printf '%d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ] || exit 1
[ "$pass" -gt 0 ] || { echo "nothing ran"; exit 1; }
