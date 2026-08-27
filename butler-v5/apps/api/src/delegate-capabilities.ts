/**
 * Default subagent capabilities when the caller omits `capabilities`.
 * Scheme B: developer role gets exec tools on Child Run.
 */
export function defaultCapabilitiesForRole(role: string): readonly string[] {
  const normalized = role.trim().toLowerCase()
  if (normalized === "developer" || normalized === "dev") {
    return ["read_file", "write_file", "run_command"]
  }
  return ["general"]
}
