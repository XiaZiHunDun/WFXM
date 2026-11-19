#!/usr/bin/env node
/**
 * 存量测试内部分诊：找出“只断言内部实现、没有任何用户可见结果断言”的用例。
 *
 * 纯静态扫描，不执行测试、不新增依赖。判据：
 *   内部信号：toHaveBeenCalled*、vi.fn/spyOn、eventType/event_store、
 *             sqlite_master/PRAGMA/CREATE TABLE、prompt 文本断言、注册表长度
 *   结果信号：reply/response/status/finalDecision/workspace/exitCode/stdout、
 *             toMatch、resolves/rejects、fetch/request
 * 两者同时出现视为“有结果锚点”，不计入候选。
 *
 * 用法：
 *   node scripts/audit/test-internal-assertions.mjs
 *   node scripts/audit/test-internal-assertions.mjs --min 1 --top 40 --details
 *   node scripts/audit/test-internal-assertions.mjs --json > audit.json
 */
import { readdirSync, readFileSync, writeFileSync } from "node:fs"
import { join, relative, sep } from "node:path"

const ROOT = process.cwd()
const SKIP_DIRS = new Set([
  ".git",
  "node_modules",
  "dist",
  "coverage",
  ".eval-runs",
  ".turbo",
  ".pnpm-store",
])

const INTERNAL_SIGNALS = [
  ["mock-call", /toHaveBeenCalled(?:Times|With|Once)?\b|toHaveBeenNthCalledWith\b|\.mock\.calls\b/],
  ["mock-setup", /\bvi\.(?:fn|spyOn|mock)\(|\bjest\.(?:fn|spyOn|mock)\(/],
  [
    "event-row",
    /\beventType\b|\bevent_store\b|\beventStore\b|\bsqlite_master\b|\bPRAGMA\s+table_info\b|\bCREATE\s+TABLE\b/i,
  ],
  [
    "prompt-text",
    /\b(?:systemPrompt|system_prompt|prompt)\b[^;\n]{0,120}\.(?:toContain|toEqual|toBe)\(/i,
  ],
  ["registry-size", /\b(?:registry|registrations?|toolsById)\b[^;\n]{0,80}toHaveLength\(/i],
]

const OUTCOME_SIGNALS = [
  ["reply", /\b(?:reply|replies|finalDecision|finalReplyPattern)\b/],
  ["result", /\b(?:response|status|body|exitCode|stdout|stderr|workspace|workspaceState)\b/],
  ["assert-outcome", /\btoMatch\(|\bresolves\.|\brejects\.|\bexpectFile\b/],
  ["envelope", /\.to(?:Equal|StrictEqual)\(\s*\{/],
  ["result-var", /\bexpect\(\s*(?:result|res|reply|out|envelope|error|err|value|response|body)\b/],
  ["io", /\b(?:fetch\(|request\(|sendWechatMessage\()/],
]

const LEGACY_TAG = /\bR8\.x\.\d+|\bD\d{1,2}\b|§\d+/g

function parseArgs(argv) {
  const opts = { json: false, details: false, min: 2, top: 25 }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === "--json") opts.json = true
    else if (arg === "--details") opts.details = true
    else if (arg === "--min") opts.min = Number(argv[++i] ?? opts.min)
    else if (arg === "--top") opts.top = Number(argv[++i] ?? opts.top)
  }
  return opts
}

function walk(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue
    const abs = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) walk(abs, out)
      continue
    }
    if (entry.isFile() && abs.endsWith(".test.ts")) out.push(abs)
  }
}

function isIdentStart(ch) {
  return /[A-Za-z_$]/.test(ch)
}

function isIdentChar(ch) {
  return /[A-Za-z0-9_$]/.test(ch)
}

/** 跳过字符串字面量，返回结束引号之后的下标。 */
function skipString(src, start) {
  const quote = src[start]
  let i = start + 1
  while (i < src.length) {
    if (src[i] === "\\") {
      i += 2
      continue
    }
    if (src[i] === quote) return i + 1
    i += 1
  }
  return i
}

/** 从 `open` 处的左括号找到匹配的右括号，跳过字符串与注释。 */
function matchParen(src, open) {
  let depth = 0
  let i = open
  while (i < src.length) {
    const ch = src[i]
    if (ch === "/" && src[i + 1] === "/") {
      const nl = src.indexOf("\n", i)
      i = nl < 0 ? src.length : nl + 1
      continue
    }
    if (ch === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2)
      i = end < 0 ? src.length : end + 2
      continue
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      i = skipString(src, i)
      continue
    }
    if (ch === "(") depth += 1
    else if (ch === ")") {
      depth -= 1
      if (depth === 0) return i
    }
    i += 1
  }
  return src.length - 1
}

function lineOf(src, index) {
  let line = 1
  for (let i = 0; i < index; i += 1) if (src[i] === "\n") line += 1
  return line
}

function extractName(block) {
  const match = block.match(/^\(\s*(["'`])((?:\\[\s\S]|(?!\1)[\s\S])*?)\1/)
  if (!match) return "(anonymous)"
  return match[2].replace(/\\n/g, " ").slice(0, 120)
}

/** 找出所有 it()/test() 调用块（不处理 it.each，避免误切）。 */
function findTestBlocks(src) {
  const blocks = []
  let i = 0
  while (i < src.length) {
    const ch = src[i]
    if (ch === "/" && src[i + 1] === "/") {
      const nl = src.indexOf("\n", i)
      i = nl < 0 ? src.length : nl + 1
      continue
    }
    if (ch === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2)
      i = end < 0 ? src.length : end + 2
      continue
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      i = skipString(src, i)
      continue
    }
    if (isIdentStart(ch)) {
      const start = i
      while (i < src.length && isIdentChar(src[i])) i += 1
      const word = src.slice(start, i)
      if ((word === "it" || word === "test") && src[i] === "(") {
        const end = matchParen(src, i)
        blocks.push({
          name: extractName(src.slice(i, end + 1)),
          text: src.slice(i, end + 1),
          line: lineOf(src, start),
        })
        i = end + 1
        continue
      }
      continue
    }
    i += 1
  }
  return blocks
}

function categoryOf(relPath) {
  if (relPath.startsWith("tests/architecture")) return "架构不变量"
  if (relPath.startsWith("tests/contracts")) return "契约"
  if (relPath.startsWith("tests/integration")) return "集成"
  if (relPath.startsWith("tests/eval") || relPath.startsWith("tests/acceptance")) return "场景"
  return "单测"
}

function classify(text, relPath) {
  const internal = INTERNAL_SIGNALS.filter(([name, re]) => {
    if (!re.test(text)) return false
    // 持久化层的职责就是事件/表行，行断言属于该层的结果而非内部实现。
    if (name === "event-row" && relPath.startsWith("packages/persistence/")) return false
    return true
  }).map(([name]) => name)
  const outcome = OUTCOME_SIGNALS.filter(([, re]) => re.test(text)).map(([name]) => name)
  return { internal, outcome, internalOnly: internal.length > 0 && outcome.length === 0 }
}

function main() {
  const opts = parseArgs(process.argv.slice(2))
  const files = []
  walk(ROOT, files)

  let totalTests = 0
  let internalOnlyTotal = 0
  const perFile = []

  for (const abs of files) {
    const rel = relative(ROOT, abs).split(sep).join("/")
    const src = readFileSync(abs, "utf8")
    const blocks = findTestBlocks(src)
    if (blocks.length === 0) continue
    const flagged = []
    for (const block of blocks) {
      const verdict = classify(block.text, rel)
      if (verdict.internalOnly) {
        flagged.push({ name: block.name, line: block.line, signals: verdict.internal })
      }
    }
    totalTests += blocks.length
    internalOnlyTotal += flagged.length
    const legacyTags = [...new Set(src.match(LEGACY_TAG) ?? [])]
    perFile.push({
      file: rel,
      layer: categoryOf(rel),
      tests: blocks.length,
      internalOnly: flagged.length,
      ratio: flagged.length / blocks.length,
      legacyTags,
      flagged,
    })
  }

  perFile.sort(
    (a, b) => b.internalOnly - a.internalOnly || b.ratio - a.ratio || a.file.localeCompare(b.file),
  )
  const candidates = perFile.filter((entry) => entry.internalOnly >= opts.min)
  const report = {
    generatedAt: new Date().toISOString(),
    totals: {
      files: perFile.length,
      tests: totalTests,
      internalOnly: internalOnlyTotal,
      ratio: totalTests === 0 ? 0 : internalOnlyTotal / totalTests,
    },
    files: candidates.slice(0, opts.top),
    allFiles: perFile,
  }

  if (opts.json) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n")
    return
  }

  const pct = (value) => `${(value * 100).toFixed(1)}%`
  console.log(
    `\n测试内部分诊 — ${report.totals.files} 文件 / ${report.totals.tests} 用例，内部-only ${report.totals.internalOnly}（${pct(report.totals.ratio)}）`,
  )
  console.log(`\ninternal-only ≥ ${opts.min} 的文件（按数量排序）：\n`)
  console.log("| 文件 | 层 | internal-only | 用例 | 占比 | 历史标签 |")
  console.log("|------|----|---------------|------|------|----------|")
  for (const entry of report.files) {
    console.log(
      `| ${entry.file} | ${entry.layer} | ${entry.internalOnly} | ${entry.tests} | ${pct(entry.ratio)} | ${entry.legacyTags.join(" ") || "—"} |`,
    )
  }

  if (opts.details) {
    console.log("\n候选用例：\n")
    for (const entry of report.files) {
      for (const item of entry.flagged) {
        console.log(`- ${entry.file}:${item.line} — ${item.name} [${item.signals.join(", ")}]`)
      }
    }
  }

  console.log(
    `\n共 ${candidates.length} 个文件达到阈值；用 --details 查看具体用例，--json 输出机器可读结果。`,
  )
  console.log("统计口径：只扫描显式 it/test 块，it.each 与循环生成的用例不计。")
  console.log("注意：这是候选清单，删除前仍需确认对应契约/集成/评测任务已覆盖。")
}

main()
