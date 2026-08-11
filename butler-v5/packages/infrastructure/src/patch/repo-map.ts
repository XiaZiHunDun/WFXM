// infrastructure/patch/repo-map.ts
// 文件重要性评分 [OPT-14] — 基于目录 + 配置的简单评分（替代 PageRank）

import type { LoadBearingMark } from "@butler/domain"

// ─── 文件重要性评分 ─────────────────────────────────────
export function scoreFileImportance(path: string, marks: readonly LoadBearingMark[]): number {
  let score = 0

  // 1. 承重代码标记：直接加 50
  const matched = marks.find((m) => m.path === path)
  if (matched?.ownerApproved) {
    score += 50
  }

  // 2. 目录权重
  if (path.includes("core/") || path.includes("domain/")) score += 30
  else if (path.includes("infrastructure/") || path.includes("application/")) score += 20
  else if (path.includes("gateway/") || path.includes("ports/")) score += 15
  else if (path.includes("config/") || path.includes("shared/")) score += 10

  // 3. 文件类型权重
  if (path.endsWith(".ts") && !path.endsWith(".test.ts")) score += 10
  if (path.endsWith(".py")) score += 5
  if (path.endsWith(".test.ts") || path.endsWith(".spec.ts")) score += 5
  if (path.endsWith("index.ts") || path.endsWith("__init__.py")) score += 5

  // 4. 文件大小权重（估算）
  const depth = path.split("/").length
  if (depth <= 3) score += 5

  return Math.min(score, 100)
}

// ─── 构建仓库 Map ───────────────────────────────────────
export function buildRepoMap(
  files: readonly string[],
  marks: readonly LoadBearingMark[],
): Map<string, number> {
  const map = new Map<string, number>()
  for (const file of files) {
    map.set(file, scoreFileImportance(file, marks))
  }
  return map
}

// ─── 获取 Top-K 重要文件 ────────────────────────────────
export function topKImportant(
  files: readonly string[],
  marks: readonly LoadBearingMark[],
  k: number = 10,
): readonly string[] {
  const scored = files.map((f) => ({ file: f, score: scoreFileImportance(f, marks) }))
  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, k).map((s) => s.file)
}
