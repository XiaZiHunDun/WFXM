/** Natural-language → /切换 normalization (shared with project surface). */
export function normalizeWechatSwitchCommand(content: string): string | null {
  const stripped = content.trim().replace(/[。.!！?？]+$/u, "")
  const switchPrefixes = ["切换到", "切换至", "切换去", "切换回"]
  if (
    stripped.startsWith("切换") &&
    !switchPrefixes.some((prefix) => stripped.startsWith(prefix))
  ) {
    const name = stripped.slice("切换".length).trim().replace(/[。.!！?？]+$/u, "")
    if (name && !name.startsWith("/")) {
      return `/切换 ${name}`
    }
  }
  for (const prefix of [
    "切换到",
    "切换至",
    "切换去",
    "切换回",
    "现在切到",
    "现在切回",
    "切到",
    "切回",
    "把项目切回去",
    "把项目切回",
  ]) {
    if (stripped.startsWith(prefix)) {
      const name = stripped.slice(prefix.length).trim().replace(/[。.!！?？]+$/u, "")
      if (name) return `/切换 ${name}`
    }
  }
  if (stripped.startsWith("切回去")) {
    const name = stripped.slice("切回去".length).trim().replace(/[。.!！?？]+$/u, "")
    if (name) return `/切换 ${name}`
  }
  return null
}
