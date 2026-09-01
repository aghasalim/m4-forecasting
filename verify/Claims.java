// The claims the README makes in prose, which no table contains and nothing
// recomputes.
//
// Section 1 is mostly arithmetic on the summary tables: an interval "41% wider"
// than another, "fifteen times the narrowest", a "16-point shortfall", "4 to 13
// times wider", the MSIS that is "worse in every case". Those ratios were
// worked out by hand once and typed into the page. The tables themselves are
// checked elsewhere; these derived numbers were checked by nobody, and two of
// them, the Weekly 94.9% coverage and theta's 1.288 OWA, do not appear in any
// table at all, so nothing else in this harness would notice if they drifted.
//
// Each check below does two things: it requires the sentence to still be in
// README.md as written, and it recomputes its number from reports/summary_*.csv.
// Editing the prose without the data, or the data without the prose, fails.
//
// Run: java verify/Claims.java <root>

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class Claims {

    static String readme;
    static int failures = 0;
    static int checked = 0;

    /** One published summary row. */
    record Row(String method, String interval, Map<String, Double> values) {
        double get(String field) {
            Double v = values.get(field);
            if (v == null) throw new IllegalStateException("no column " + field);
            return v;
        }
    }

    static List<Row> load(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path);
        String[] header = lines.get(0).split(",");
        List<Row> rows = new ArrayList<>();
        for (String line : lines.subList(1, lines.size())) {
            if (line.isBlank()) continue;
            String[] cells = line.split(",");
            if (cells.length != header.length)
                throw new IllegalStateException(path + " has a ragged row: " + line);
            Map<String, Double> values = new HashMap<>();
            String method = null, interval = null;
            for (int i = 0; i < header.length; i++) {
                switch (header[i]) {
                    case "method" -> method = cells[i];
                    case "interval" -> interval = cells[i];
                    default -> values.put(header[i], Double.parseDouble(cells[i]));
                }
            }
            rows.add(new Row(method, interval, values));
        }
        return rows;
    }

    static Row find(List<Row> rows, String method, String interval) {
        for (Row r : rows)
            if (r.method().equals(method) && r.interval().equals(interval))
                return r;
        throw new IllegalStateException("no row for " + method + "/" + interval);
    }

    /** The sentence must still be in the README, and its number must still be
     *  what the summary files say, to `decimals` places. */
    static void claim(String label, String fragment, double published, double computed, int decimals) {
        checked++;
        boolean present = readme.contains(fragment.replaceAll("\\s+", " "));
        double tol = 0.5 * Math.pow(10, -decimals) + 1e-9;
        boolean agrees = Math.abs(published - computed) <= tol;
        String status = present && agrees ? "ok" : "FAIL";
        if (!present || !agrees) failures++;
        System.out.printf("  %-38s \"%s\"%s  computed %.4f  %s%n",
                label, fragment, present ? "" : " NOT IN README", computed, status);
    }

    /** A claim with no number of its own: an ordering, or a sign. */
    static void holds(String label, String fragment, boolean condition) {
        checked++;
        boolean present = readme.contains(fragment.replaceAll("\\s+", " "));
        if (!present || !condition) failures++;
        System.out.printf("  %-38s \"%s\"%s  %s%n", label, fragment,
                present ? "" : " NOT IN README", present && condition ? "ok" : "FAIL");
    }

    public static void main(String[] args) throws IOException {
        Path root = Path.of(args.length > 0 ? args[0] : ".");
        // Line breaks in the source of a paragraph are not part of the claim,
        // so both sides are compared with runs of whitespace collapsed.
        readme = Files.readString(root.resolve("README.md")).replaceAll("\\s+", " ");
        List<Row> hourly = load(root.resolve("reports/summary_Hourly.csv"));
        List<Row> weekly = load(root.resolve("reports/summary_Weekly.csv"));

        Row snA = find(hourly, "seasonal_naive", "analytic");
        Row snE = find(hourly, "seasonal_naive", "empirical");

        System.out.println("coverage against the nominal 95%, on Hourly");
        Row widest = hourly.get(0), narrowest = hourly.get(0);
        Row bestCover = hourly.get(0), worstCover = hourly.get(0), worstMsis = hourly.get(0);
        for (Row r : hourly) {
            if (r.get("width") > widest.get("width")) widest = r;
            if (r.get("width") < narrowest.get("width")) narrowest = r;
            if (r.get("coverage95") > bestCover.get("coverage95")) bestCover = r;
            if (r.get("coverage95") < worstCover.get("coverage95")) worstCover = r;
            if (r.get("MSIS") > worstMsis.get("MSIS")) worstMsis = r;
        }
        claim("the best coverage on Hourly", "The best is 93.9%", 93.9,
                100 * bestCover.get("coverage95"), 1);
        holds("and it is the widest interval", "it is the widest interval on the board",
                bestCover == widest);
        claim("the worst coverage on Hourly", "worst case 79.1% against a nominal 95%", 79.1,
                100 * worstCover.get("coverage95"), 1);
        claim("its shortfall from nominal", "a 16-point shortfall", 16,
                95 - 100 * worstCover.get("coverage95"), 0);
        claim("widest over narrowest interval", "fifteen times the narrowest", 15,
                widest.get("width") / narrowest.get("width"), 0);

        System.out.println("\nwidth is what coverage costs");
        claim("the worst MSIS on the board", "naive analytic worst of all at 71.24", 71.24,
                worstMsis.get("MSIS"), 2);
        List<Row> byWidth = new ArrayList<>(hourly);
        byWidth.sort((a, b) -> Double.compare(b.get("width"), a.get("width")));
        List<Row> byMsis = new ArrayList<>(hourly);
        byMsis.sort((a, b) -> Double.compare(b.get("MSIS"), a.get("MSIS")));
        boolean sameThree = byWidth.subList(0, 3).containsAll(byMsis.subList(0, 3));
        holds("the widest three are the worst three",
                "the three widest rows are the three worst on it", sameThree);

        System.out.println("\nmeasuring your errors against trusting your model");
        double wider = 100 * (snA.get("width") / snE.get("width") - 1);
        double narrower = 100 * (1 - snE.get("width") / snA.get("width"));
        claim("seasonal_naive analytic is wider by", "41% wider than its empirical one", 41, wider, 0);
        claim("the same gap read the other way", "at 29% narrower", 29, narrower, 0);
        holds("and it covers less while wider", "still covers less, 85.2% against 86.6%",
                snA.get("coverage95") < snE.get("coverage95"));
        claim("its MSIS analytic", "MSIS drops from 11.06 to 8.82", 11.06, snA.get("MSIS"), 2);
        claim("its MSIS empirical", "MSIS drops from 11.06 to 8.82", 8.82, snE.get("MSIS"), 2);

        double lo = Double.MAX_VALUE, hi = 0;
        boolean msisWorseEverywhere = true;
        for (String m : new String[] {"naive", "naive2", "theta", "seasonal_naive"}) {
            Row a = find(hourly, m, "analytic"), e = find(hourly, m, "empirical");
            msisWorseEverywhere &= a.get("MSIS") > e.get("MSIS");
            if (m.equals("seasonal_naive")) continue;   // the exception the text carves out
            double ratio = a.get("width") / e.get("width");
            lo = Math.min(lo, ratio);
            hi = Math.max(hi, ratio);
        }
        claim("the other three, narrowest ratio", "4 to 13 times wider", 4, Math.floor(lo), 0);
        claim("the other three, widest ratio", "4 to 13 times wider", 13, Math.floor(hi), 0);
        holds("analytic MSIS worse on all four", "its MSIS is worse in every case", msisWorseEverywhere);

        System.out.println("\nthe ranking, and the two Weekly numbers no table carries");
        Row bestOwa = hourly.get(0), bestMsis = hourly.get(0);
        for (Row r : hourly) {
            if (r.get("OWA") < bestOwa.get("OWA")) bestOwa = r;
            if (r.get("MSIS") < bestMsis.get("MSIS")) bestMsis = r;
        }
        claim("the best OWA on Hourly", "an **OWA of 0.843**", 0.843, bestOwa.get("OWA"), 3);
        holds("which is seasonal_naive", "`seasonal_naive` takes an **OWA of 0.843**", bestOwa.method().equals("seasonal_naive"));
        holds("best MSIS is the bold row",
                "The bold row is the best MSIS, not the best coverage",
                bestMsis.method().equals("seasonal_naive") && bestMsis.interval().equals("empirical"));
        claim("theta on Hourly", "scores **1.013**", 1.013,
                find(hourly, "theta", "analytic").get("OWA"), 3);
        holds("worse than the naive2 baseline", "worse than the naive2 baseline",
                find(hourly, "theta", "analytic").get("OWA")
                        > find(hourly, "naive2", "analytic").get("OWA"));
        claim("theta on Weekly", "worse still, at 1.288", 1.288,
                find(weekly, "theta", "analytic").get("OWA"), 3);

        int nominal = 0;
        for (Row r : weekly)
            if (r.interval().equals("analytic")
                    && Math.abs(100 * r.get("coverage95") - 94.9) <= 0.05 + 1e-9)
                nominal++;
        claim("Weekly analytic rows at 94.9%", "land on 94.9% for three of the four methods",
                3, nominal, 0);
        claim("the calibrated Weekly interval", "(94.9% against 95%)", 94.9,
                100 * find(weekly, "seasonal_naive", "analytic").get("coverage95"), 1);

        if (failures > 0) {
            System.out.printf("%n%d of %d claims in the prose no longer hold%n", failures, checked);
            System.exit(1);
        }
        System.out.printf("%nall %d derived claims in the README still follow from reports/%n", checked);
    }
}
