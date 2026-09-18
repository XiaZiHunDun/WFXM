/**
 * D72 T5 (audit #18 CQ-001): `redactSecrets` + `containsSecret` DELETED
 * (only test consumers existed — pure dead code). The two functions
 * that ARE used by production (conversation-loop.ts:17) are preserved:
 * `redactSecretText` (in-loop redactor) and `shouldRedactToolResults`
 * (env-toggled feature gate).
 *
 * The deleted exports were a candidate for adoption into audit emit
 * sites (JSON.stringify patterns in audit-fatigue.ts) but that
 * tightening is deferred to D73+ as a separate security track.
 */
const REDACTED_PLACEHOLDER = "[REDACTED]"
const TOKEN_KEY_PATTERN = /(token|password|secret|api[_-]?key|authorization)/i

/**
 * Decide whether tool-result text redaction should run for this
 * conversation loop iteration. Gated on the
 * `BUTLER_V5_REDACT_TOOL_RESULTS` env var so operators can disable
 * if their downstream tooling needs raw values (e.g. for debugging).
 */
export function shouldRedactToolResults(env: NodeJS.ProcessEnv): boolean {
  const raw = env["BUTLER_V5_REDACT_TOOL_RESULTS"]
  if (raw === undefined) return true
  const v = raw.trim().toLowerCase()
  return v === "1" || v === "true" || v === "yes" || v === "on"
}

/**
 * Redact well-known secret-bearing tokens from tool-result text.
 * Conservative — masks substrings shaped like GitHub personal access
 * tokens (ghp_/gho_/ghs_/ghr_/ghu_ + 30+ alphanumeric) and generic
 * JSON-ish `"key":"value"` lines where the key matches TOKEN_KEY_PATTERN.
 *
 * Returns the input unchanged when no secrets are detected. Never
 * throws — failures fall through to the input.
 */
export function redactSecretText(text: string): string {
  try {
    let out = text
    // GitHub PAT family: ghp_/gho_/ghs_/ghr_/ghu_ + 30+ alphanumeric/underscore
    out = out.replace(/\b(gh[pousr]_[A-Za-z0-9_]{30,})\b/g, REDACTED_PLACEHOLDER)
    // Generic JSON-ish key:value where key looks secret-bearing
    out = out.replace(
      new RegExp(
        `(["'])(?:${TOKEN_KEY_PATTERN.source})\\1\\s*:\\s*(["'])([^"']{4,})\\2`,
        "gi",
      ),
      (_match, q1: string, q2: string) => `${q1}${TOKEN_KEY_PATTERN.source.split("|")[0]}${q1}:${q2}${REDACTED_PLACEHOLDER}${q2}`,
    )
    return out
  } catch {
    return text
  }
}