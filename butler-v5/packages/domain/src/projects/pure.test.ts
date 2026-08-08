import { describe, it, expect } from "vitest"
import {
  validateProjectPath,
  validateSpec,
  isSpecStale,
  validateDelegateTaskInput,
  sortProjectsByCreated,
  searchProjects,
  activateProject,
  archiveProject,
  blockProject,
  createProject,
} from "./pure.js"
import type { Project, ProjectId, Spec, DelegateTaskInput, WorkspaceRoot } from "./types.js"

const sampleProject: Project = {
  id: "proj-1" as Project["id"],
  name: "Test Project",
  rootPath: "/home/user/projects/test",
  specRef: "spec-1",
  createdAt: 1000,
  status: "active",
  blockedReason: null,
}

const sampleSpec: Spec = {
  id: "spec-1",
  project: "proj-1" as Spec["project"],
  documents: {
    spec: "需求文档内容",
    design: "设计文档内容",
    tasks: "任务列表",
    plan: "计划文档",
  },
  createdAt: 1000,
  updatedAt: Date.now(),
}

describe("projects/pure", () => {
  describe("validateProjectPath", () => {
    it("accepts valid path", () => {
      expect(validateProjectPath("/home/user/projects/test")).toEqual({ valid: true })
    })
    it("rejects empty path", () => {
      const result = validateProjectPath("")
      expect(result.valid).toBe(false)
      expect(result.reason).toContain("不能为空")
    })
    it("rejects path with ..", () => {
      const result = validateProjectPath("/home/../etc")
      expect(result.valid).toBe(false)
      expect(result.reason).toContain("..")
    })
  })

  describe("validateSpec", () => {
    it("accepts complete spec", () => {
      expect(validateSpec(sampleSpec)).toEqual({ valid: true, missing: [] })
    })
    it("reports missing documents", () => {
      const incomplete: Spec = {
        ...sampleSpec,
        documents: { spec: "x", design: "", tasks: "", plan: "" },
      }
      const result = validateSpec(incomplete)
      expect(result.valid).toBe(false)
      expect(result.missing).toContain("design")
      expect(result.missing).toContain("tasks")
      expect(result.missing).toContain("plan")
    })
  })

  describe("isSpecStale", () => {
    it("returns false for recent spec", () => {
      expect(isSpecStale(sampleSpec)).toBe(false)
    })
    it("returns true for old spec", () => {
      const oldSpec: Spec = {
        ...sampleSpec,
        updatedAt: Date.now() - 8 * 24 * 60 * 60 * 1000,
      }
      expect(isSpecStale(oldSpec)).toBe(true)
    })
    it("respects custom maxAge", () => {
      const spec = { ...sampleSpec, updatedAt: Date.now() - 60_000 }
      expect(isSpecStale(spec, 30_000)).toBe(true)
      expect(isSpecStale(spec, 120_000)).toBe(false)
    })
  })

  describe("validateDelegateTaskInput", () => {
    it("accepts valid input", () => {
      const input: DelegateTaskInput = {
        projectId: "proj-1" as DelegateTaskInput["projectId"],
        specRef: "spec-1",
      }
      expect(validateDelegateTaskInput(input, sampleProject)).toEqual({ valid: true })
    })
    it("rejects mismatched project ID", () => {
      const input: DelegateTaskInput = {
        projectId: "proj-2" as DelegateTaskInput["projectId"],
        specRef: "spec-1",
      }
      const result = validateDelegateTaskInput(input, sampleProject)
      expect(result.valid).toBe(false)
      expect(result.reason).toContain("不匹配")
    })
    it("rejects empty specRef", () => {
      const input: DelegateTaskInput = {
        projectId: "proj-1" as DelegateTaskInput["projectId"],
        specRef: "",
      }
      const result = validateDelegateTaskInput(input, sampleProject)
      expect(result.valid).toBe(false)
      expect(result.reason).toContain("specRef")
    })
  })

  describe("sortProjectsByCreated", () => {
    it("sorts newest first", () => {
      const projects: readonly Project[] = [
        { ...sampleProject, id: "a" as Project["id"], createdAt: 1000 },
        { ...sampleProject, id: "b" as Project["id"], createdAt: 3000 },
        { ...sampleProject, id: "c" as Project["id"], createdAt: 2000 },
      ]
      const sorted = sortProjectsByCreated(projects)
      expect(sorted[0]?.id).toBe("b")
      expect(sorted[1]?.id).toBe("c")
      expect(sorted[2]?.id).toBe("a")
    })
  })

  describe("searchProjects", () => {
    it("finds projects by name", () => {
      const projects: readonly Project[] = [
        { ...sampleProject, id: "a" as Project["id"], name: "Alpha" },
        { ...sampleProject, id: "b" as Project["id"], name: "Beta" },
      ]
      const results = searchProjects(projects, "alpha")
      expect(results).toHaveLength(1)
      expect(results[0]?.name).toBe("Alpha")
    })
    it("returns empty for no match", () => {
      const results = searchProjects([sampleProject], "zzz")
      expect(results).toHaveLength(0)
    })
  })
})

describe("project lifecycle", () => {
  const id = "proj-1" as ProjectId
  const root = "/ws" as WorkspaceRoot

  it("creates a project with active state", () => {
    const p = createProject({ id, name: "Demo", workspaceRoot: root })
    expect(p.status).toBe("active")
    expect(p.createdAt).toBeGreaterThan(0)
  })
  it("blocks and unblocks a project", () => {
    let p = createProject({ id, name: "Demo", workspaceRoot: root })
    p = blockProject(p, "audit")
    expect(p.status).toBe("blocked")
    p = activateProject(p)
    expect(p.status).toBe("active")
  })
  it("archives a project", () => {
    let p = createProject({ id, name: "Demo", workspaceRoot: root })
    p = archiveProject(p)
    expect(p.status).toBe("archived")
  })
})
