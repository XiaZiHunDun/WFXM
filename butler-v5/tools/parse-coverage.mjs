#!/usr/bin/env node
/**
 * D53b coverage parser — one-shot. Parses vitest --coverage JSON output
 * into per-package baseline. Committed to tools/ for future D54+ baselines.
 *
 * Run: cd butler-v5 && node tools/parse-coverage.mjs
 * Reads: coverage/coverage-summary.json
 * Writes: tools/coverage-baseline.json
 */
import { readFileSync, writeFileSync } from "node:fs";

const summaryPath = "coverage/coverage-summary.json";
const outPath = "tools/coverage-baseline.json";

const summary = JSON.parse(readFileSync(summaryPath, "utf8"));
const baseline = {
  snapshotDate: "2026-09-11",
  shipEvent: "D53b",
  total: summary.total,
  packages: {},
  files: {},
};

// Group by package — vitest paths are absolute (e.g. /home/.../butler-v5/packages/domain/src/foo.ts)
for (const [file, data] of Object.entries(summary)) {
  if (file === "total") continue;
  // Extract package from path: .../butler-v5/packages/<pkg>/src/... or .../butler-v5/apps/<app>/src/...
  const match = file.match(/\/(?:packages|apps)\/([^/]+)\/src\//);
  const pkg = match ? match[1] : "other";
  if (!baseline.packages[pkg]) {
    baseline.packages[pkg] = { files: 0, lineSum: 0, branchSum: 0, functionSum: 0, statementSum: 0 };
  }
  baseline.packages[pkg].files += 1;
  baseline.packages[pkg].lineSum += data.lines?.pct ?? 0;
  baseline.packages[pkg].branchSum += data.branches?.pct ?? 0;
  baseline.packages[pkg].functionSum += data.functions?.pct ?? 0;
  baseline.packages[pkg].statementSum += data.statements?.pct ?? 0;
  // Store per-file data with a project-relative path for readability
  const relMatch = file.match(/\/butler-v5\/(.+)$/);
  const relPath = relMatch ? relMatch[1] : file;
  baseline.files[relPath] = data;
}

// Compute per-package averages (straight mean of per-file %; weighted form is in total)
for (const pkg of Object.keys(baseline.packages)) {
  const p = baseline.packages[pkg];
  const f = p.files;
  baseline.packages[pkg] = {
    files: f,
    lines: f > 0 ? +(p.lineSum / f).toFixed(2) : 0,
    branches: f > 0 ? +(p.branchSum / f).toFixed(2) : 0,
    functions: f > 0 ? +(p.functionSum / f).toFixed(2) : 0,
    statements: f > 0 ? +(p.statementSum / f).toFixed(2) : 0,
  };
}

// Find low-coverage modules (< 50% lines) — flagged for follow-up
const lowCoverage = Object.entries(summary)
  .filter(([file, data]) => file !== "total" && (data.lines?.pct ?? 100) < 50)
  .map(([file, data]) => ({
    file: file.match(/\/butler-v5\/(.+)$/)?.[1] ?? file,
    lines: data.lines?.pct,
    branches: data.branches?.pct,
    functions: data.functions?.pct,
  }))
  .sort((a, b) => (a.lines ?? 100) - (b.lines ?? 100));

baseline.lowCoverageModules = lowCoverage;

writeFileSync(outPath, JSON.stringify(baseline, null, 2) + "\n");
console.log("Written coverage-baseline.json");
console.log("Total:", JSON.stringify(baseline.total, null, 2));
console.log("Packages:", Object.keys(baseline.packages).length);
console.log("Files:", Object.keys(baseline.files).length);
console.log("Low coverage modules (< 50% lines):", lowCoverage.length);