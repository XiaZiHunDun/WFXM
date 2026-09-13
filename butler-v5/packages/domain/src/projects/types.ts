// domain/projects/types.ts
// 项目域 ADT — Project + ProjectId + Spec SDD + DelegateTaskInput
// D62 T5 (audit #2 F-02/F-03): removed WorkspaceRoot + ProjectStatus —
// zero external consumers (D61 T5 deleted the only 4 fns in
// projects/pure.ts that used them). Project is kept since pure.ts
// still references it for the sortProjectsByCreated/searchProjects
// APIs (zero external consumers but kept for completeness).

// ─── 品牌类型 ───────────────────────────────────────────
export type ProjectId = string & { readonly __brand: "ProjectId" }

// ─── 项目定义 ───────────────────────────────────────────
export type Project = {
  readonly id: ProjectId
  readonly name: string
  readonly rootPath: string
  readonly specRef?: string
  readonly createdAt: number
  readonly status: "active" | "blocked" | "archived"
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
