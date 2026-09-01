// Structural validation of everything under reports/, and a check that the
// tables in the README still say what those files say.
//
// The CSVs under reports/ are the evidence for every number in the README, and
// nothing checked they are well formed: a truncated write, a column that
// drifted, an Inf out of a division by a zero scale would all be invisible
// until someone read a table. Worse, the README is typed by hand from the
// summary files, so a number can be right in reports/ and wrong on the page
// that people actually read. This walks every results file, then reads the two
// tables out of README.md and compares every figure in them, at the precision
// each figure is printed to, against reports/summary_Hourly.csv.
package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// Expected shape of the results files, from the README's own claims.
var expected = map[string]struct{ rows, series int }{
	"raw_Hourly.csv": {3312, 414},
	"raw_Weekly.csv": {2872, 359},
}

type table struct {
	header []string
	rows   [][]string
}

func readCSV(path string) (*table, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.FieldsPerRecord = 0 // a ragged file is an error, which is the point
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) < 2 {
		return nil, fmt.Errorf("only %d rows", len(rows))
	}
	return &table{header: rows[0], rows: rows[1:]}, nil
}

func (t *table) col(name string) int {
	for i, h := range t.header {
		if h == name {
			return i
		}
	}
	return -1
}

func (t *table) num(row []string, name string) (float64, error) {
	i := t.col(name)
	if i < 0 {
		return 0, fmt.Errorf("no column %q", name)
	}
	return strconv.ParseFloat(strings.TrimSpace(row[i]), 64)
}

// Ranges every column of the results files must stay inside. A coverage of 1.4
// or a negative width is not a small error, it is a broken metric.
var ranges = map[string][2]float64{
	"smape": {0, 200}, "sMAPE": {0, 200},
	"mase": {0, 1e6}, "MASE": {0, 1e6},
	"owa": {0, 1e6}, "OWA": {0, 1e6},
	"cover95": {0, 1}, "coverage95": {0, 1},
	"width": {0, 1e9}, "msis": {0, 1e9}, "MSIS": {0, 1e9},
}

func validate(path string) []string {
	var problems []string
	t, err := readCSV(path)
	if err != nil {
		return []string{fmt.Sprintf("unreadable: %v", err)}
	}

	seen := map[string]bool{}
	for _, h := range t.header {
		if strings.TrimSpace(h) == "" {
			problems = append(problems, "a column has an empty name")
		}
		if seen[h] {
			problems = append(problems, fmt.Sprintf("duplicate column %q", h))
		}
		seen[h] = true
	}

	for i, row := range t.rows {
		for j, cell := range row {
			c := strings.TrimSpace(cell)
			low := strings.ToLower(c)
			if c == "" {
				problems = append(problems,
					fmt.Sprintf("row %d column %s is empty", i+2, t.header[j]))
				continue
			}
			if low == "nan" || low == "inf" || low == "-inf" || low == "infinity" {
				problems = append(problems,
					fmt.Sprintf("row %d column %s is %s", i+2, t.header[j], c))
				continue
			}
			r, ok := ranges[t.header[j]]
			if !ok {
				continue
			}
			v, err := strconv.ParseFloat(c, 64)
			if err != nil {
				problems = append(problems,
					fmt.Sprintf("row %d column %s is not a number: %q", i+2, t.header[j], c))
				continue
			}
			if math.IsNaN(v) || math.IsInf(v, 0) || v < r[0] || v > r[1] {
				problems = append(problems,
					fmt.Sprintf("row %d column %s is %v, outside [%g, %g]",
						i+2, t.header[j], v, r[0], r[1]))
			}
		}
	}

	base := filepath.Base(path)
	if want, ok := expected[base]; ok {
		if len(t.rows) != want.rows {
			problems = append(problems,
				fmt.Sprintf("%d data rows, expected %d", len(t.rows), want.rows))
		}
		ids := map[string]bool{}
		if c := t.col("series"); c >= 0 {
			for _, row := range t.rows {
				ids[row[c]] = true
			}
		}
		if len(ids) != want.series {
			problems = append(problems,
				fmt.Sprintf("%d distinct series, expected %d", len(ids), want.series))
		}
	}
	if strings.HasPrefix(base, "summary_") && len(t.rows) != 8 {
		problems = append(problems,
			fmt.Sprintf("%d summary rows, expected 8 (4 methods x 2 intervals)", len(t.rows)))
	}
	return problems
}

// --- the README tables ----------------------------------------------------

// A markdown table row split on pipes, with bold markers and footnotes removed.
func cells(line string) []string {
	line = strings.TrimSpace(line)
	line = strings.TrimPrefix(line, "|")
	line = strings.TrimSuffix(line, "|")
	parts := strings.Split(line, "|")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		p = strings.ReplaceAll(p, "**", "")
		p = strings.TrimSpace(strings.TrimSuffix(p, "(baseline)"))
		out = append(out, p)
	}
	return out
}

// Rows of the first table whose header cells start with the given prefix.
func findTable(lines []string, want []string) [][]string {
	for i, ln := range lines {
		if !strings.HasPrefix(strings.TrimSpace(ln), "|") {
			continue
		}
		head := cells(ln)
		if len(head) != len(want) {
			continue
		}
		match := true
		for k := range want {
			if head[k] != want[k] {
				match = false
				break
			}
		}
		if !match {
			continue
		}
		var rows [][]string
		for j := i + 2; j < len(lines); j++ { // +2 skips the |---| separator
			if !strings.HasPrefix(strings.TrimSpace(lines[j]), "|") {
				break
			}
			rows = append(rows, cells(lines[j]))
		}
		return rows
	}
	return nil
}

// Published figures are rounded to however many decimals they are printed
// with, so each is allowed half a unit in its own last digit and no more.
func agrees(published string, computed float64) (float64, float64, bool) {
	published = strings.TrimSuffix(published, "%")
	v, err := strconv.ParseFloat(published, 64)
	if err != nil {
		return 0, 0, false
	}
	decimals := 0
	if dot := strings.Index(published, "."); dot >= 0 {
		decimals = len(published) - dot - 1
	}
	tol := 0.5*math.Pow(10, -float64(decimals)) + 1e-9
	return v, tol, math.Abs(v-computed) <= tol
}

func main() {
	root := flag.String("root", ".", "repository root")
	flag.Parse()

	reports := filepath.Join(*root, "reports")
	files, err := filepath.Glob(filepath.Join(reports, "*.csv"))
	if err != nil || len(files) == 0 {
		fmt.Fprintf(os.Stderr, "no CSVs under %s\n", reports)
		os.Exit(2)
	}
	sort.Strings(files)

	bad := 0
	fmt.Printf("validating %d results files under reports/\n", len(files))
	for _, path := range files {
		problems := validate(path)
		bad += len(problems)
		for _, p := range problems {
			fmt.Printf("  %s: %s\n", filepath.Base(path), p)
		}
	}
	if bad == 0 {
		fmt.Println("  no ragged rows, duplicate columns, empty cells, NaN, Inf or out of range values")
		fmt.Println("  row and series counts are the ones the README claims")
	}

	// The README tables, against the summary they were typed from.
	md, err := os.ReadFile(filepath.Join(*root, "README.md"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read README.md: %v\n", err)
		os.Exit(2)
	}
	lines := strings.Split(string(md), "\n")

	summary, err := readCSV(filepath.Join(reports, "summary_Hourly.csv"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "summary_Hourly.csv: %v\n", err)
		os.Exit(2)
	}
	find := func(method, interval string) []string {
		mc, ic := summary.col("method"), summary.col("interval")
		for _, r := range summary.rows {
			if r[mc] == method && r[ic] == interval {
				return r
			}
		}
		return nil
	}

	check := func(label, published string, computed float64) {
		v, tol, ok := agrees(published, computed)
		status := "ok"
		if !ok {
			status = "FAIL"
			bad++
		}
		fmt.Printf("  %-34s README %-8s reports %-10.4f |d| %.4f (tol %.4f)  %s\n",
			label, published, computed, math.Abs(v-computed), tol, status)
	}

	fmt.Println("\nthe interval table in README.md, against reports/summary_Hourly.csv")
	rows := findTable(lines, []string{"method", "interval", "coverage (nominal 95%)", "width", "MSIS"})
	if len(rows) != 8 {
		fmt.Printf("  found %d rows in the interval table, expected 8\n", len(rows))
		bad++
	}
	for _, r := range rows {
		src := find(r[0], r[1])
		if src == nil {
			fmt.Printf("  %s/%s is in the README but not in summary_Hourly.csv\n", r[0], r[1])
			bad++
			continue
		}
		cov, _ := summary.num(src, "coverage95")
		width, _ := summary.num(src, "width")
		msis, _ := summary.num(src, "MSIS")
		label := r[0] + "/" + r[1]
		check(label+" coverage", r[2], 100*cov)
		check(label+" width", r[3], width)
		check(label+" MSIS", r[4], msis)
	}

	fmt.Println("\nthe point accuracy table in README.md")
	rows = findTable(lines, []string{"Hourly", "sMAPE", "MASE", "OWA"})
	if len(rows) != 4 {
		fmt.Printf("  found %d rows in the point accuracy table, expected 4\n", len(rows))
		bad++
	}
	for _, r := range rows {
		src := find(r[0], "analytic")
		if src == nil {
			fmt.Printf("  %s is in the README but not in summary_Hourly.csv\n", r[0])
			bad++
			continue
		}
		smape, _ := summary.num(src, "sMAPE")
		mase, _ := summary.num(src, "MASE")
		owa, _ := summary.num(src, "OWA")
		check(r[0]+" sMAPE", r[1], smape)
		check(r[0]+" MASE", r[2], mase)
		check(r[0]+" OWA", r[3], owa)
	}

	// The series counts, which the README states in prose three times.
	fmt.Println("\nthe series counts in the prose")
	counts := map[string]int{}
	for _, freq := range []string{"Hourly", "Weekly"} {
		t, err := readCSV(filepath.Join(reports, "raw_"+freq+".csv"))
		if err != nil {
			fmt.Fprintf(os.Stderr, "raw_%s.csv: %v\n", freq, err)
			os.Exit(2)
		}
		ids := map[string]bool{}
		c := t.col("series")
		for _, r := range t.rows {
			ids[r[c]] = true
		}
		counts[freq] = len(ids)
	}
	text := string(md)
	if m := regexp.MustCompile(`(\d+) Hourly and (\d+) Weekly series`).FindStringSubmatch(text); m != nil {
		check("Hourly series", m[1], float64(counts["Hourly"]))
		check("Weekly series", m[2], float64(counts["Weekly"]))
	} else {
		fmt.Println("  the README no longer states the two series counts")
		bad++
	}
	if m := regexp.MustCompile(`are (\d+) of M4's 100,000`).FindStringSubmatch(text); m != nil {
		check("Hourly plus Weekly", m[1], float64(counts["Hourly"]+counts["Weekly"]))
	} else {
		fmt.Println("  the README no longer states the combined count")
		bad++
	}

	if bad > 0 {
		fmt.Printf("\n%d problems\n", bad)
		os.Exit(1)
	}
	fmt.Println("\nreports/ is well formed and every figure in the README tables matches it")
}
