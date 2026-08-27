/**
 * P2 Credential host-injection port.
 *
 * Secrets are owned by the host and injected only at the execution boundary.
 * The model, audit and context artifacts only ever see credential *names*,
 * never values. Providers enumerate availability and resolve values on demand;
 * resolution must fail closed for unknown names.
 */
export interface CredentialProvider {
  /** Names the host can currently resolve (names only, never values). */
  readonly availableCredentials: () => Promise<readonly string[]>
  /** Resolve the values for the requested names. Rejects if any name is unknown. */
  readonly resolveCredentials: (
    names: readonly string[],
  ) => Promise<Readonly<Record<string, string>>>
}

/** A credential name must be an env-safe token (upper/lower/digit/underscore). */
export function isValidCredentialName(name: string): boolean {
  return /^[A-Za-z0-9_]{1,64}$/.test(name)
}