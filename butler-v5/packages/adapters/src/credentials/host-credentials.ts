/**
 * P2 host-held credential provider (an env/secret-store adapter).
 *
 * Values are loaded once from `BUTLER_V5_CREDENTIALS` (a JSON map name→value)
 * and are only ever handed to the resolution caller at the execution boundary.
 * `availableCredentials` returns names only; unknown or malformed names fail
 * closed.
 */
import type { CredentialProvider } from "@butler/ports/core/credential-provider.js"
import { isValidCredentialName } from "@butler/ports/core/credential-provider.js"

/** Parse `name→value` map from a JSON string. Returns null when unset/not JSON. */
export function parseHostCredentials(raw: string | undefined): Readonly<Record<string, string>> | null {
  if (raw === undefined || raw.trim() === "") return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === "string") out[k] = v
    }
    return out
  } catch {
    return null
  }
}

export function createHostCredentialProvider(
  env: Readonly<Record<string, string | undefined>> = {},
  loader: (raw: string | undefined) => Readonly<Record<string, string>> | null = parseHostCredentials,
): CredentialProvider {
  return {
    async availableCredentials() {
      const map = loader(env["BUTLER_V5_CREDENTIALS"])
      if (!map) return []
      return Object.keys(map).filter(isValidCredentialName)
    },
    async resolveCredentials(names) {
      const map = loader(env["BUTLER_V5_CREDENTIALS"]) ?? {}
      const out: Record<string, string> = {}
      for (const name of names) {
        if (!isValidCredentialName(name)) {
          throw new Error(`invalid credential name: ${name}`)
        }
        const value = map[name]
        if (value === undefined) {
          throw new Error(`credential not resolvable: ${name}`)
        }
        out[name] = value
      }
      return out
    },
  }
}

/**
 * Authorize and inject host-held credentials into a command's child env.
 *
 * Only names present on the host allowlist may be resolved; the resolved values
 * are merged into `baseEnv` (fail-closed). The caller's persisted args/audit
 * retain only the *names*, so values never enter context artifacts.
 */
export async function injectRunCommandCredentials(opts: {
  readonly provider: CredentialProvider
  readonly requestedNames: readonly string[]
  readonly allowlist: readonly string[]
  readonly baseEnv: Readonly<Record<string, string>>
}): Promise<{ readonly ok: true; readonly env: Record<string, string> } | { readonly ok: false; readonly reason: string }> {
  const requested = [...new Set(opts.requestedNames)]
  if (requested.length === 0) {
    return { ok: true, env: { ...opts.baseEnv } }
  }
  const allow = new Set(opts.allowlist)
  for (const name of requested) {
    if (!allow.has(name)) {
      return { ok: false, reason: `credential not authorized for run_command: ${name}` }
    }
  }
  let resolved: Readonly<Record<string, string>>
  try {
    resolved = await opts.provider.resolveCredentials(requested)
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
  return { ok: true, env: { ...opts.baseEnv, ...resolved } }
}