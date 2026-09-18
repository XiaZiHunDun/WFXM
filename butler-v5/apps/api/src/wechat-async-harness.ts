/**
 * D72 T5 (audit #18 CQ-004): pollMockOutboxForText removed (was the
 * only consumer of this file's other helper — test fixture masquerading
 * as production module per CQ-004). Only `waitForCondition` is kept
 * here because 3 test cases (wechat-dev-delegate.test.ts) still rely
 * on the generic polling helper.
 */
export async function waitForCondition(
  predicate: () => Promise<boolean>,
  opts: { readonly timeoutMs?: number; readonly intervalMs?: number } = {},
): Promise<boolean> {
  const timeoutMs = opts.timeoutMs ?? 120_000
  const intervalMs = opts.intervalMs ?? 50
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await predicate()) return true
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return predicate()
}