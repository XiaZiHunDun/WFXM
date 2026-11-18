# Changelog

All notable changes to Butler v5 are documented here.

## [0.0.1] — 2026-07-31

### Architecture

- Initial FC/IS (Functional Core / Imperative Shell) architecture
- 6 domain modules: conversation, tools, memory, workflows, projects, permissions
- 11 Effect-TS Port Tags: LLMService, ToolExecutor, EventStoreService, LoopInterrupt, GuardService, WeChatGateway, MCPDiscovery, ProjectService, MemoryService, WorkflowService, Config
- 10 GUARD mechanisms: evidence gating, load-bearing protection, owner offline, human sig, multi-file chain, verification level, role separation, 3-layer self-heal, anti-pattern archive, chaos drill
- Event Sourcing + CQRS with DeltaChannel
- 7-level decision ladder for development
- Scope boundary 4-column table

### Packages

- `@butler/domain` — 6-domain ADT + pure functions
- `@butler/ports` — 11 Effect-TS Context Tags
- `@butler/application` — 4 use cases (runLoop, delegateTask, runWorkflow, dream)
- `@butler/infrastructure` — Layer implementations + adapters
- `@butler/config` — Single Schema configuration with @effect/schema
- `@butler/shared` — Cross-package utilities

### Testing

- 3062 tests across 293 files
- Domain pure function tests (zero mock)
- Application orchestration tests (Mock Layer injection)
- Infrastructure integration tests
- Guard tests (architecture constraint verification)
- Meta-audit tests (mock integrity + circular dependency detection)
- Contract tests (Port stability + ConfigSchema validation)

### Development Standards

- `.editorconfig` + `.prettierrc` + `.prettierignore`
- `.nvmrc` + `.node-version` (Node.js 20)
- Enhanced ESLint rules (no-throw-literal, consistent-type-imports, prefer-readonly)
- `.gitignore` includes `*.tsbuildinfo`, `.env.local`
- `hooks/` PreToolUse + PostToolUse (protected file checks, auto-test on edit)
- `scripts/run-test-layer.sh` — layered test runner
- `scripts/typecheck-gate.sh` — typecheck + file size + protected file check
- `.butler/` configuration (scope-boundaries, load-bearing-marks, anti-patterns)
- GitHub Actions CI (typecheck + test with PostgreSQL)

### Documentation

- `README.md` — project overview
- `DESIGN.md` — architecture design reference
- `AGENTS.md` — AI coding tool behavior contract
- `.cursorrules` — AI tool rules (BLOCK/MUST/SHOULD)
- `CONTRIBUTING.md` — contribution guide
- `.env.example` — environment variable template
