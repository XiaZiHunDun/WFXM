# Vendored pi agent core

Source: https://github.com/earendil-works/pi
Package: `packages/agent` (`@earendil-works/pi-agent-core@1.5.2`)
Copy date: 2026-11-17
Upstream commit: `6273031b0`

Files under `src/` are copied from the upstream package, with two deltas:

1. Imports resolve through the published `@earendil-works/pi-ai` and
   `@earendil-works/pi-schema` packages pinned in `package.json`.
2. `agent-loop.ts` has three non-null assertions on indexed accesses
   (`context.messages[...]!`, `pendingMessages[i]!`) so the file also
   compiles under Butler's `noUncheckedIndexedAccess` when the runtime
   package type-checks it. No behavioral change.

License: MIT (see `LICENSE`).
