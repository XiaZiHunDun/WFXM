/**
 * Default subagent capabilities when the caller omits `capabilities`.
 * Scheme B: developer role gets exec tools on Child Run.
 *
 * `exec` / `executor` 同义：真实对话里模型常把执行类任务委派为 role="exec"，
 * 若只认 developer 会退化成 ["general"]，子代理拿不到 write_file / run_command。
 */
const EXEC_ROLES: ReadonlySet<string> = new Set([
  "developer",
  "dev",
  "exec",
  "executor",
  "engineer",
  "coder",
])

export function defaultCapabilitiesForRole(role: string): readonly string[] {
  const normalized = role.trim().toLowerCase()
  if (EXEC_ROLES.has(normalized)) {
    return ["read_file", "write_file", "run_command"]
  }
  return ["general"]
}
