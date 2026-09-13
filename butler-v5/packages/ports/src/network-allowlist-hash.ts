/**
 * D61 T5 (audit #2 F-11 domain purity): moved from
 * `packages/domain/src/governance/network-allowlist.ts` because it imports
 * `node:crypto`. Domain must remain pure (no node built-ins); ports is
 * the appropriate layer for SHA-256 hashing utilities.
 *
 * Re-exported from `@butler/domain/governance/network-allowlist` for
 * backward compatibility with existing call sites (runtime/approval-runtime).
 */
import { createHash } from "node:crypto"

export function hashNetworkAllowlistForAudit(entries: readonly string[]): string {
  return createHash("sha256").update(entries.join("\n")).digest("hex").slice(0, 16)
}
