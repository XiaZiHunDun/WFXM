export const HIGH_SENSITIVITY_TOOLS: ReadonlyArray<string> = [
  "send_*",
  "delete_*",
  "external_write",
  "broadcast_*",
]

export const DEFAULT_CHECKLIST_ITEMS: ReadonlyArray<string> = [
  "我已读此操作的后果，且操作不可撤销。",
  "我确认目标对象正确（recipient / path / target）。",
]

export type SensitivityLevel = 'high' | 'normal'

export interface SensitivityMatch {
  readonly level: SensitivityLevel
  readonly items: ReadonlyArray<string>
}

function globToRegex(glob: string): RegExp {
  const escaped = glob.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")
  return new RegExp(`^${escaped}`)
}

export function matchSensitivity(toolName: string): SensitivityMatch | null {
  for (const pattern of HIGH_SENSITIVITY_TOOLS) {
    if (globToRegex(pattern).test(toolName)) {
      return { level: "high", items: DEFAULT_CHECKLIST_ITEMS }
    }
  }
  return null
}