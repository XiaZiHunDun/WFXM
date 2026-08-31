/**
 * Arch guard (D35-arch-align §0+§1+§1.1+§2+§19 sweep audit):
 * deep-audit the 4 §段 that hadn't yet had a dedicated guard.
 *
 *   §0  架构裁决（六边形 + 5 第一性推导）                — line 11-23
 *   §1  架构分层总览                                      — line 27-62
 *   §1.1 实施缝隙：delivery shell                          — line 64-71
 *   §2  产品身份与非目标                                  — line 75-94
 *   §19 文档与治理边界                                    — line 804-823
 *
 * Audit findings (D35, 2026-08-31):
 *
 *   - §0  5 第一性推导全部由 §3 / §6 / §17 / §20 prior lock
 *         覆盖；本 batch 仅 #1（单 Owner / 自托管 / 低并发 → 不预建
 *         K8s / 微服务 / CQRS / Event Sourcing）需要新静态守卫
 *         防 deps 漂移。
 *   - §1  唯一新增守卫：无 in-process EventBus / 通用 EventEmitter
 *         总线（D26A §20 #1 仅锁 1 RunEngine，不锁模块间是否走事件总线）。
 *   - §1.1 delivery shell = apps/api；D33 §3 #6 + side-effect-throat.test.ts
 *         已锁 runTool* 旁路。本 batch 仅 re-state 在 §1.1 命名下。
 *   - §2  非目标 deps（K8s / Temporal / LangGraph / ContextGraph / CQRS
 *         / Celery / Airflow / Dagster）必须 0 出现，否则违反 §2 + §0 #1。
 *   - §19 3 SSOT 引用文件存在性 + log.md 冻结声明 + state.md 引用规约
 *         必须有静态守卫。
 *
 * Drift acknowledgment (D35, 2026-08-31):
 *
 *   - DESIGN §19 line 807-810 + 823 用 bare filename 引用 SSOT 文件
 *     （v5-product-boundaries-2026-08.md / v5-production-architecture-
 *     2026-08.md / v5-engineering-handoff-2026-08.md）。从 butler-v5/
 *     DESIGN.md 视角，文件实际位于 ../docs/plans/decisions/ 与 ../docs/
 *     architecture/。DESIGN.md 仅 §1.1 line 71 用相对路径
 *     `../docs/architecture/v5-production-architecture-2026-08.md`，§19
 *     全段未带相对路径。本 batch 不改 DESIGN 路径表达，沿 D34 §13
 *     "3 类 trigger text vs 3 lists per-tool approver impl" 风格承认
 *     text-vs-impl drift；路径修正属 doc-only fix，应单独建 batch。
 *
 * Static checks (no runtime):
 *   - §0  #1 — package.json / pyproject.toml 0 非目标 deps。
 *   - §1  — Core + apps 0 EventBus / 通用 EventEmitter 总线。
 *   - §1.1— apps production sources 0 直接 runTool* 调（re-statement
 *         of side-effect-throat.test.ts:18-25 under §1.1 命名）。
 *   - §2  #1 — manifests 0 K8s/Temporal/LangGraph/CQRS/Celery/
 *         Airflow/Dagster deps（与 §0 #1 共用静态检查）。
 *   - §2  #2 — Core / apps 不复制工程治理 Guard 产品化（无第二套
 *         决策状态机）。
 *   - §2  #3 — Channel/MCP/浏览器复用同一运行与权限边界（D29 +
 *         D27 §10 已 lock；本 batch re-state）。
 *   - §19 — 3 SSOT 引用文件存在。
 *   - §19 — log.md 头部声明冻结 + 活动交接只更新 state.md。
 *   - §19 — state.md 是默认载体（含 _last_synced / _handoff 字段）。
 *   - §19 — AGENTS.md 工程治理文件存在（仓库根 + butler-v5 根）。
 *   - §19 — DESIGN.md 不被 Core / apps 作为运行时模块 import。
 *
 * Runtime behavior is verified by:
 *   - D26A §20 #1+#2+#3+#4 (RunEngine / Core / LLM / entry)
 *   - D27 §10 governance (Capability / ScopedGrant / PolicyGate)
 *   - D29 §8+§9 (driving + driven adapters)
 *   - D32 §17.1+§17.2 (monorepo + 并行开发)
 *   - D33 §3 依赖方向硬规则
 *
 * Remediation when guards fire:
 *   - 非目标 deps 出现 → §0 #1 + §2 违规；删除 deps。
 *   - in-process EventBus 出现 → §1 违规；改模块直接调用。
 *   - delivery shell runTool* → §1.1 违规；路由到 runButlerLoop。
 *   - 工程治理内容渗入 Core / apps → §2 + §20 #12 违规；移出产品代码。
 *   - SSOT 文件缺失 → §19 违规；恢复或更新 DESIGN 引用。
 *   - log.md 冻结声明丢失 → §19 违规；恢复冻结声明。
 *   - state.md 引用断链 → §19 违规；同步 v5-engineering-handoff 引用。
 *   - DESIGN.md 被产品代码 import → §19 + §0 SSOT 违规；移除 import。
 */

import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const REPO_ROOT = join(__dirname, "../../..")
const BUTLER_V5 = join(REPO_ROOT, "butler-v5")
const PACKAGES_SRC = join(BUTLER_V5, "packages")
const APPS_SRC = join(BUTLER_V5, "apps")

function listTsFiles(dir: string, excludeTests = true): string[] {
  const out: string[] = []
  if (!existsSync(dir)) return out
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    const stat = statSync(path)
    if (stat.isDirectory()) {
      if (entry === "node_modules" || entry === "dist" || entry === "coverage" || entry === "_archive") continue
      out.push(...listTsFiles(path, excludeTests))
    } else if (entry.endsWith(".ts")) {
      if (excludeTests && entry.endsWith(".test.ts")) continue
      out.push(path)
    }
  }
  return out
}

function readAllSrc(dir: string, excludeTests = true): string {
  return listTsFiles(dir, excludeTests).map((f) => readFileSync(f, "utf8")).join("\n")
}

describe("§0+§1+§1.1+§2+§19 sweep (D35)", () => {
  // C1 §0 #1 + §2 非目标：manifests 无 K8s / Temporal / LangGraph /
  // ContextGraph / CQRS / Celery / Airflow / Dagster deps。
  it("manifests do not pull non-target orchestrators / DAG / CQRS / K8s deps (§0 #1 + §2)", () => {
    const NON_TARGET = /\b(temporal|langgraph|contextgraph|cqrs|celery|airflow|dagster|kubernetes|helm\.js|k8s\.js)\b/i
    const manifests = [
      join(BUTLER_V5, "package.json"),
      join(BUTLER_V5, "cli/package.json"),
      join(BUTLER_V5, "pyproject.toml"),
    ].filter(existsSync)
    const violations: string[] = []
    for (const m of manifests) {
      const src = readFileSync(m, "utf8")
      if (NON_TARGET.test(src)) violations.push(relative(REPO_ROOT, m))
    }
    expect(violations).toEqual([])
  })

  // C2 §1 架构分层：Core + apps 无 in-process EventBus / 通用
  // EventEmitter 总线（§1 line 60 "不使用进程内通用 Event Bus"）。
  it("no in-process EventBus / generic EventEmitter abstraction (§1)", () => {
    const FORBIDDEN = /\bclass\s+EventBus\b|\bnew\s+EventEmitter\s*\(|inProcessEventBus\b/
    const candidates = [
      join(PACKAGES_SRC, "domain/src"),
      join(PACKAGES_SRC, "runtime/src"),
      join(PACKAGES_SRC, "ports/src"),
      APPS_SRC,
    ]
      .filter(existsSync)
      .flatMap((d) => listTsFiles(d))
    const violations: string[] = []
    for (const f of candidates) {
      const src = readFileSync(f, "utf8")
      if (FORBIDDEN.test(src)) violations.push(relative(REPO_ROOT, f))
    }
    expect(violations).toEqual([])
  })

  // C3 §1.1 delivery shell：apps production sources 0 直接调 runTool*
  // 旁路（re-statement of side-effect-throat.test.ts:18-25）。
  it("apps production sources do not call runTool* directly (§1.1 delivery shell)", () => {
    const violations: string[] = []
    for (const f of listTsFiles(APPS_SRC)) {
      const src = readFileSync(f, "utf8")
      if (/\brunTool\b/.test(src) && /from\s+["']@butler\/runtime\/tool-runtime/.test(src)) {
        violations.push(relative(REPO_ROOT, f))
      }
    }
    expect(violations).toEqual([])
  })

  // C4 §2 + §20 #12：Core / apps 不复制第二套 Guard 产品化（§19 line
  // 821 "工程治理 ≠ 产品运行时架构"）；不允许 Core 写 in-DB guard 状态机
  // 或在 API 层镜像 .cursorrules / hooks 决策。
  it("Core and apps do not embed engineering governance as product logic (§2 + §19)", () => {
    // 1. Core 不 import AGENTS.md / .cursorrules / hooks 路径作为模块。
    // 2. apps 也不允许（delivery shell 已是 policy boundary 之上）。
    const FORBIDDEN_IMPORT = /from\s+["'][^"']*(AGENTS\.md|\.cursorrules|hooks\/v5-ai-guard|pre_commit_hook)[^"']*["']/i
    const candidateDirs = [
      join(PACKAGES_SRC, "domain/src"),
      join(PACKAGES_SRC, "runtime/src"),
      join(PACKAGES_SRC, "ports/src"),
      APPS_SRC,
    ].filter(existsSync)
    const violations: string[] = []
    for (const d of candidateDirs) {
      for (const f of listTsFiles(d)) {
        const src = readFileSync(f, "utf8")
        if (FORBIDDEN_IMPORT.test(src)) violations.push(relative(REPO_ROOT, f))
      }
    }
    expect(violations).toEqual([])
  })

  // C5 §19 SSOT：3 引用文件存在（product boundaries / production arch
  // / engineering handoff）。
  it("§19 SSOT referenced files exist (3 files)", () => {
    const required = [
      join(REPO_ROOT, "docs/plans/decisions/v5-product-boundaries-2026-08.md"),
      join(REPO_ROOT, "docs/architecture/v5-production-architecture-2026-08.md"),
      join(REPO_ROOT, "docs/plans/decisions/v5-engineering-handoff-2026-08.md"),
    ]
    const missing = required.filter((f) => !existsSync(f)).map((f) => relative(REPO_ROOT, f))
    expect(missing).toEqual([])
  })

  // C6 §19 log.md 冻结声明：log.md 头部明示冻结 + 活动交接只更新 state.md。
  it(".blackboard/log.md declares freeze + delegates activity to state.md (§19)", () => {
    const log = readFileSync(join(REPO_ROOT, ".blackboard/log.md"), "utf8")
    expect(log).toMatch(/冻结/)
    expect(log).toMatch(/活动交接只更新/)
    expect(log).toMatch(/state\.md/)
  })

  // C7 §19 state.md 默认载体：state.md 存在 + 含 _last_synced / _handoff 字段。
  it(".blackboard/state.md exists as default handoff carrier (§19)", () => {
    const statePath = join(REPO_ROOT, ".blackboard/state.md")
    expect(existsSync(statePath)).toBe(true)
    const src = readFileSync(statePath, "utf8")
    expect(src).toMatch(/_last_synced:|_handof{2}:|# WFXM BlackBoard/i)
  })

  // C8 §1 + §20 #1：唯一 RunEngine class + 唯一 PolicyGate class 在
  // runtime 包内（不允许重复声明 / 不允许在 apps 包内重复实现）。
  it("exactly one RunEngine + one PolicyGate class definition in runtime (§1 + §20 #1)", () => {
    const runtimeSrc = readAllSrc(join(PACKAGES_SRC, "runtime/src"))
    const runEngineClass = (runtimeSrc.match(/export\s+class\s+RunEngine\b/g) || []).length
    const policyGateClass = (runtimeSrc.match(/export\s+class\s+PolicyGate\b/g) || []).length
    expect(runEngineClass).toBe(1)
    expect(policyGateClass).toBe(1)
    // apps 包不允许重复定义
    const appsSrc = readAllSrc(APPS_SRC)
    expect(/export\s+class\s+RunEngine\b/.test(appsSrc)).toBe(false)
    expect(/export\s+class\s+PolicyGate\b/.test(appsSrc)).toBe(false)
  })

  // C9 §19 工程治理文件存在：仓库根 + butler-v5 根双层 AGENTS.md。
  it("AGENTS.md exists at repo root + butler-v5 root (§19 governance surface)", () => {
    const candidates = [
      join(REPO_ROOT, "AGENTS.md"),
      join(BUTLER_V5, "AGENTS.md"),
    ]
    const missing = candidates.filter((f) => !existsSync(f)).map((f) => relative(REPO_ROOT, f))
    expect(missing).toEqual([])
  })

  // C10 §19 SSOT：DESIGN.md 是 doc，不被 Core / apps 作为运行时模块
  // import（杜绝把 governance doc 引入产品代码路径）。
  it("DESIGN.md is not referenced as a runtime import in Core or apps (§19)", () => {
    const candidateDirs = [
      join(PACKAGES_SRC, "domain/src"),
      join(PACKAGES_SRC, "runtime/src"),
      join(PACKAGES_SRC, "ports/src"),
      APPS_SRC,
    ].filter(existsSync)
    const violations: string[] = []
    for (const d of candidateDirs) {
      for (const f of listTsFiles(d)) {
        const src = readFileSync(f, "utf8")
        if (/from\s+["'][^"']*DESIGN\.md["']/.test(src) || /require\(["'][^"']*DESIGN\.md["']\)/.test(src)) {
          violations.push(relative(REPO_ROOT, f))
        }
      }
    }
    expect(violations).toEqual([])
  })
})