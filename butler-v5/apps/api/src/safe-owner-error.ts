/**
 * D61 T1 (audit #3 cluster E): defensive wrap that converts caught errors into
 * owner-safe Chinese messages while preserving full error context for
 * operator logs.
 *
 * Background: D60 audit (#3 F-04/05/06/08, #1 F-07/08/09) found 8+ sites
 * where raw `${err.message}` leaked into owner-facing surfaces. That pattern
 * exposes DB connection strings, ENOSPC errno+path, internal stack frames,
 * and capability names. This helper enforces "log full, return safe" by
 * accepting a Chinese fallback the caller already vetted.
 *
 * Usage:
 *   } catch (err) {
 *     return safeOwnerError(err, "运行失败，请稍后重试", { operation: "run-task" })
 *   }
 *
 * Contract:
 *   - Always returns the fallback (never raw err.message).
 *   - Always logs structured context to stderr for operators.
 *   - If `err` is an Error, captures name/message/stack; otherwise String(err).
 *   - Caller is responsible for picking an owner-friendly Chinese fallback.
 */
export type SafeOwnerErrorContext = Readonly<Record<string, unknown>>

export function safeOwnerError(
  err: unknown,
  fallback: string,
  context?: SafeOwnerErrorContext,
): string {
  const errInfo =
    err instanceof Error
      ? { name: err.name, message: err.message, stack: err.stack }
      : { value: String(err) }
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error("[safe-owner-error]", {
    ...errInfo,
    context: context ?? null,
    fallback,
  })
  return fallback
}
