/**
 * P2 runtime secret scan / redaction.
 *
 * Reuses the detector from `@butler/domain/observability/local-trace.js` so
 * pattern sets stay in one place. All-or-nothing redaction is applied at the
 * persistence/egress boundaries; the live tool→model messages are redacted only
 * under `BUTLER_V5_REDACT_TOOL_RESULTS=1` so the agent keeps reading raw output
 * by default.
 */
import { redactTraceText, redactTraceValue } from "@butler/domain/observability/local-trace.js"

/** Redact a string in place (sk-*, ghp_*, AKIA, JWT, Bearer, key=value). */
export function redactSecretText(text: string): string {
  return redactTraceText(text)
}

/** Deep-redact an unknown value (keys named token/password/etc. masked). */
export function redactSecrets(value: unknown): unknown {
  return redactTraceValue(value, 0)
}

/** True when `value` contains any discoverable secret-bearing token/value. */
export function containsSecret(value: unknown): boolean {
  let probe: string
  try {
    probe = JSON.stringify(value) ?? ""
  } catch {
    probe = String(value)
  }
  return probe !== (JSON.stringify(redactTraceValue(value, 0)) ?? "")
}

/** Read the strict-mode flag for tool-result/context redaction (default off). */
export function shouldRedactToolResults(env: Readonly<Record<string, string | undefined>> = {}): boolean {
  const raw = env["BUTLER_V5_REDACT_TOOL_RESULTS"]
  if (raw === undefined || raw.trim() === "") return false
  return raw.trim().toLowerCase() === "1" || raw.trim().toLowerCase() === "true"
}