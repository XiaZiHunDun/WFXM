// domain/projects/pure.ts
// 项目域纯函数 — Spec 校验、委派任务输入验证

import type {
  Project,
  ProjectId,
  ProjectStatus,
  Spec,
  DelegateTaskInput,
  WorkspaceRoot,
} from "./types.js"

// ─── 项目路径校验 ───────────────────────────────────────
export function validateProjectPath(rootPath: string): { valid: boolean; reason?: string } {
  if (!rootPath || rootPath.trim().length === 0) {
    return { valid: false, reason: "项目路径不能为空" }
  }
  if (rootPath.includes("..")) {
    return { valid: false, reason: "项目路径不能包含 .." }
  }
  return { valid: true }
}

// ─── Spec 四制品完整性校验 ──────────────────────────────
export function validateSpec(spec: Spec): {
  valid: boolean
  missing: readonly string[]
} {
  const missing: string[] = []
  if (!spec.documents.spec || spec.documents.spec.trim().length === 0) missing.push("spec")
  if (!spec.documents.design || spec.documents.design.trim().length === 0) missing.push("design")
  if (!spec.documents.tasks || spec.documents.tasks.trim().length === 0) missing.push("tasks")
  if (!spec.documents.plan || spec.documents.plan.trim().length === 0) missing.push("plan")
  return { valid: missing.length === 0, missing }
}

// ─── Spec 时效性检查 ────────────────────────────────────
export function isSpecStale(spec: Spec, maxAgeMs: number = 7 * 24 * 60 * 60 * 1000): boolean {
  return Date.now() - spec.updatedAt > maxAgeMs
}

// ─── DelegateTaskInput 校验 ─────────────────────────────
export function validateDelegateTaskInput(
  input: DelegateTaskInput,
  project: Project,
): { valid: boolean; reason?: string } {
  if (input.projectId !== project.id) {
    return { valid: false, reason: `项目 ID 不匹配: ${input.projectId} vs ${project.id}` }
  }
  if (!input.specRef || input.specRef.trim().length === 0) {
    return { valid: false, reason: "specRef 不能为空 [OPT-3]" }
  }
  if (project.specRef && input.specRef !== project.specRef) {
    return {
      valid: false,
      reason: `specRef 与项目默认 spec 不匹配: ${input.specRef} vs ${project.specRef}`,
    }
  }
  return { valid: true }
}

// ─── 项目列表排序（按创建时间） ──────────────────────────
export function sortProjectsByCreated(projects: readonly Project[]): readonly Project[] {
  return [...projects].sort((a, b) => b.createdAt - a.createdAt)
}

// ─── 项目名称模糊搜索 ───────────────────────────────────
export function searchProjects(projects: readonly Project[], query: string): readonly Project[] {
  const q = query.toLowerCase()
  return projects.filter((p) => p.name.toLowerCase().includes(q) || p.id.toLowerCase().includes(q))
}

// ─── 项目生命周期状态机 ──────────────────────────────────
export function createProject(input: {
  id: ProjectId
  name: string
  workspaceRoot: WorkspaceRoot
}): Project {
  return {
    id: input.id,
    name: input.name,
    rootPath: input.workspaceRoot,
    status: "active" as ProjectStatus,
    createdAt: Date.now(),
    blockedReason: null,
  }
}

export function activateProject(p: Project): Project {
  return { ...p, status: "active" as ProjectStatus, blockedReason: null }
}

export function blockProject(p: Project, reason: string): Project {
  if (p.status === "archived") {
    return p
  }
  return { ...p, status: "blocked" as ProjectStatus, blockedReason: reason }
}

export function archiveProject(p: Project): Project {
  return { ...p, status: "archived" as ProjectStatus, blockedReason: null }
}
