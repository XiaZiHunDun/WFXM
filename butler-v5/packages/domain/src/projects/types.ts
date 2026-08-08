// domain/projects/types.ts
// 项目域 ADT — Project、Spec SDD、DelegateTaskInput

// ─── 品牌类型 ───────────────────────────────────────────
export type ProjectId = string & { readonly __brand: "ProjectId" }
export type WorkspaceRoot = string & { readonly __brand: "WorkspaceRoot" }

// ─── 项目生命周期状态 ──────────────────────────────────
export type ProjectStatus = "active" | "blocked" | "archived"

// ─── 项目定义 ───────────────────────────────────────────
export type Project = {
  readonly id: ProjectId
  readonly name: string
  readonly rootPath: string
  readonly specRef?: string
  readonly createdAt: number
  readonly status: ProjectStatus
  readonly blockedReason: string | null
}

// ─── Spec SDD 四制品 [OPT-3] ───────────────────────────
export type Spec = {
  readonly id: string
  readonly project: ProjectId
  readonly documents: {
    readonly spec: string
    readonly design: string
    readonly tasks: string
    readonly plan: string
  }
  readonly createdAt: number
  readonly updatedAt: number
}

// ─── delegate-task 输入（强制 Spec 引用） ──────────────
export type DelegateTaskInput = {
  readonly projectId: ProjectId
  readonly specRef: string
  readonly constraints?: readonly string[]
}
