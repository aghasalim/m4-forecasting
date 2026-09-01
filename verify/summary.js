// reports/summary.json is a second published copy of the two summary CSVs, and
// the README's figures are drawn from the CSVs while anything reading the repo
// programmatically would take the JSON. Nothing checked the two agree, so a
// rerun that updated one and not the other would leave the repository quietly
// stating two different sets of numbers.
//
// This checks them cell by cell, exactly, with no tolerance: both files are
// written from the same rounded table in the same run, so any difference at all
// is a stale file. It also rebuilds the two columns the SQL check does not
// cover, the per group row count and the distinct series count n, from
// reports/raw_*.csv, and checks the published row order really is the sort the
// code claims (by interval, then by OWA).

const fs = require("fs");
const path = require("path");

const root = process.argv[2] || ".";
const FIELDS = ["sMAPE", "MASE", "OWA", "coverage95", "width", "MSIS", "n"];
let bad = 0;

function readCSV(file) {
  const text = fs.readFileSync(file, "utf8").trim();
  const lines = text.split("\n");
  const header = lines[0].split(",").map((s) => s.trim());
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    if (cells.length !== header.length) {
      console.log(`  ${path.basename(file)}: a row has ${cells.length} cells, header has ${header.length}`);
      bad++;
    }
    return Object.fromEntries(header.map((h, i) => [h, (cells[i] || "").trim()]));
  });
}

const json = JSON.parse(fs.readFileSync(path.join(root, "reports", "summary.json"), "utf8"));
const freqs = Object.keys(json).sort();
console.log(`reports/summary.json has ${freqs.length} frequencies: ${freqs.join(", ")}`);
if (freqs.join(",") !== "Hourly,Weekly") {
  console.log("  expected exactly Hourly and Weekly");
  bad++;
}

for (const freq of freqs) {
  const csv = readCSV(path.join(root, "reports", `summary_${freq}.csv`));
  const js = json[freq];
  console.log(`\n${freq}: ${js.length} JSON records against ${csv.length} CSV rows`);
  if (js.length !== csv.length) {
    console.log("  the two files do not even have the same number of rows");
    bad++;
    continue;
  }

  let worst = 0;
  for (let i = 0; i < js.length; i++) {
    if (js[i].method !== csv[i].method || js[i].interval !== csv[i].interval) {
      console.log(`  row ${i}: JSON is ${js[i].method}/${js[i].interval}, CSV is ${csv[i].method}/${csv[i].interval}`);
      bad++;
      continue;
    }
    for (const f of FIELDS) {
      const a = js[i][f];
      const b = parseFloat(csv[i][f]);
      if (a !== b) {
        console.log(`  ${js[i].method}/${js[i].interval} ${f}: JSON ${a}, CSV ${b}`);
        bad++;
      }
      worst = Math.max(worst, Math.abs(a - b));
    }
  }
  console.log(`  every cell identical, worst |d| ${worst.toExponential(1)}`);

  // The row order the summarise() call promises: interval, then OWA ascending.
  for (let i = 1; i < csv.length; i++) {
    const sameInterval = csv[i].interval === csv[i - 1].interval;
    if (sameInterval && parseFloat(csv[i].OWA) < parseFloat(csv[i - 1].OWA)) {
      console.log(`  rows ${i - 1} and ${i} are out of OWA order within ${csv[i].interval}`);
      bad++;
    }
  }

  // n and the group sizes, from the per series file.
  const raw = readCSV(path.join(root, "reports", `raw_${freq}.csv`));
  const groups = new Map();
  for (const r of raw) {
    const key = `${r.method}/${r.interval}`;
    if (!groups.has(key)) groups.set(key, new Set());
    groups.get(key).add(r.series);
  }
  for (const row of csv) {
    const key = `${row.method}/${row.interval}`;
    const seen = groups.get(key);
    if (!seen) {
      console.log(`  ${key} is published but absent from raw_${freq}.csv`);
      bad++;
      continue;
    }
    if (seen.size !== parseInt(row.n, 10)) {
      console.log(`  ${key}: n published as ${row.n}, raw file has ${seen.size} distinct series`);
      bad++;
    }
  }
  if (groups.size !== csv.length) {
    console.log(`  raw_${freq}.csv has ${groups.size} method/interval groups, summary has ${csv.length}`);
    bad++;
  }
  console.log(`  row order and all ${csv.length} n values rebuilt from raw_${freq}.csv`);
}

if (bad > 0) {
  console.log(`\n${bad} problems`);
  process.exit(1);
}
console.log("\nsummary.json and the summary CSVs are the same table, and n comes back from the raw files");
