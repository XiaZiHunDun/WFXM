/**
 * Shared env boolean convention for apps/api: a value is truthy when its
 * trimmed lower-cased form is exactly `1`, `true`, `yes` or `on`.
 *
 * Single source of truth so feature toggles parse identically everywhere
 * (previously duplicated per module, which allowed drift e.g. missing "yes").
 */
export function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}
