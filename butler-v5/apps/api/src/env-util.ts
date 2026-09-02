/**
 * Shared env parsing conventions for apps/api: booleans and positive integers.
 *
 * Single source of truth so feature toggles parse identically everywhere
 * (previously duplicated per module, which allowed drift e.g. missing "yes").
 */
export function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

/**
 * Parse a positive integer from an env value, falling back to `fallback` when
 * the value is missing, not a finite number, or not > 0. Used for the repeated
 * `BUTLER_V5_*_MS` / `*_LIMIT` / `*_DAYS` config knobs (previously a per-module
 * local helper that drifted in name only).
 */
export function parsePositiveInt(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n > 0 ? n : fallback
}
