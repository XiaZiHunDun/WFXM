// ─── 全局错误 ADT ────────────────────────────────────────
export { type LoopError, type GuardReason, toFixSuggestion } from "./errors.js"

// ─── 对话域 ──────────────────────────────────────────────
export {
  type ConversationId,
  type LoopId,
  type MessageRole,
  type Message,
  type ToolCallPayload,
  type ConversationState,
  type ConversationEvent,
  type AgentPersona,
  type ContextWindow,
  type ContextNode,
} from "./conversation/types.js"
export { transition } from "./conversation/transitions.js"
export { makeContextWindow, isNearLimit, chooseStrategy } from "./conversation/context.js"

// ─── 工具域 ──────────────────────────────────────────────
export {
  type ToolId,
  type JSONSchema,
  type Tool,
  type ToolCall,
  type ToolResult,
  type ToolError,
  type DiscoveredTool,
} from "./tools/types.js"
export {
  classifyTool,
  validateToolCall,
  evaluateToolResult,
  isToolTimeout,
  sortToolsByPriority,
} from "./tools/pure.js"

// ─── 记忆域 ──────────────────────────────────────────────
export {
  type MemoryId,
  type MemoryRecord,
  type DreamPhase,
  type DreamResult,
} from "./memory/types.js"
export {
  scoreImportance,
  pickDreamPhase,
  pruneLowImportance,
  buildDreamResult,
} from "./memory/pure.js"

// ─── Durable Memory（知识层 2，按需）────────────────────
export {
  type DurableMemoryId,
  type DurableMemorySourceKind,
  type DurableMemoryStatus,
  type DurableMemoryProvenance,
  type DurableMemoryRecord,
  type CreateDurableMemoryInput,
  type DurableMemoryValidation,
  createDurableMemoryRecord,
  isDurableMemoryActive,
  matchDurableMemoryQuery,
  selectDurableMemoriesForWorkingSet,
  formatDurableMemoryPrefix,
  confirmDurableMemory,
  rejectDurableMemory,
} from "./knowledge/durable-memory.js"
export {
  type DocumentId,
  type DocumentFormat,
  type DocumentStatus,
  type DocumentProvenance,
  type DocumentRecord,
  type IngestDocumentInput,
  type DocumentValidation,
  DOCUMENT_FORMATS,
  defaultMimeForFormat,
  parseDocumentFormat,
  ingestDocumentRecord,
  matchDocumentQuery,
  selectDocumentsForRecall,
  formatDocumentSnippet,
} from "./knowledge/document-ingest.js"
export {
  type TaskId,
  type ProcedureId,
  type TaskStatus,
  type ProcedureStepTemplate,
  type ProcedureRecord,
  type TaskRecord,
  type CreateProcedureInput,
  type CreateTaskInput,
  type TaskValidation,
  type ProcedureValidation,
  createProcedureRecord,
  createTaskRecord,
  resolveTaskRunGoal,
  advanceTaskAfterStep,
  defaultTaskConversationId,
} from "./knowledge/task-procedure.js"

// ─── Local tracing（可观测，默认本地）────────────────────
export {
  type TraceKind,
  type TraceEvent,
  type CreateTraceEventInput,
  type TraceExporterKind,
  type TraceConfig,
  redactTraceText,
  redactTraceValue,
  createTraceEvent,
  applyTraceRedaction,
  parseTraceConfig,
  formatOtelStdoutLine,
  filterTraceEvents,
} from "./observability/local-trace.js"

// ─── 防错域 ──────────────────────────────────────────────
export {
  type IntentReceipt,
  type GuardFinding,
  type GuardName,
  type VerificationLevel,
  type LoadBearingMark,
  type LinkedFilesSpec,
  type HealLayer,
  type DeletionRisk,
  type ContractSnapshot,
  type ContractRule,
} from "./guards/types.js"
export {
  pickVerificationLevel,
  verifyChain,
  pickHealLayer,
  scoreDeletionRisk,
  verifyEvidence,
  checkRoleSeparation,
} from "./guards/pure.js"

// ─── 工作流域 ────────────────────────────────────────────
export {
  type WorkflowId,
  type Channel,
  type ChangeType,
  type SendCommand,
  type WorkflowState,
  type WorkflowEvent,
} from "./workflows/types.js"
export { workflowTransition } from "./workflows/transitions.js"

// ─── 项目域 ──────────────────────────────────────────────
export {
  type ProjectId,
  type Project,
  type Spec,
  type DelegateTaskInput,
} from "./projects/types.js"
export {
  validateProjectPath,
  validateSpec,
  isSpecStale,
  validateDelegateTaskInput,
  sortProjectsByCreated,
  searchProjects,
} from "./projects/pure.js"

// ─── 权限域 ──────────────────────────────────────────────
export { type Permission, decidePermission } from "./permissions/types.js"

// ─── 事件溯源 ────────────────────────────────────────────
export {
  projectConversation,
  loadConversation,
  type DeltaChannel,
  delta,
  buildEnvelope,
  validateEnvelope,
  type DomainEvent,
  type StreamType,
  type ActorRef,
  type EventEnvelope,
  type EnvelopeValidation,
} from "./event-sourcing.js"

// ─── Target runtime domain ───────────────────────────────
export {
  type RunId,
  type StepId,
  type TriggerSource,
  type TrustLevel,
  type RunTrigger,
  type Conversation as RuntimeConversation,
  type Message as RuntimeMessage,
  type RunStatus,
  type RunBudget,
  type Run,
  type StepKind,
  type StepStatus,
  type Step,
  canTransitionRun,
  transitionRun as transitionRuntimeRun,
  type RunTransitionResult,
} from "./runtime/index.js"
export {
  ACTIVE_MAIN_RUN_STATUSES,
  isActiveMainRunStatus,
  type StoredMessage,
  type StoredConversation,
  type StoredRun,
  type StoredStep,
  type RuntimeStore,
  type ReadModelSource,
  DEFAULT_READ_MODEL_SOURCE,
  resolveReadModelSource,
} from "./runtime/store-contract.js"
export { inferProjectIdFromConversationId } from "./runtime/project-id.js"

// ─── Governance domain ───────────────────────────────────
export {
  type RiskLevel,
  type ActionKind,
  type ActionRequest,
  type PolicyDecision,
  type ScopedGrantScope,
  type ScopedGrantRecord,
  type PermissionPolicy,
  decidePolicy,
  consumeGrantUse,
  grantMatchesAction,
  buildScopedGrantScopeFromPending,
  normalizeGrantPath,
  normalizeGrantHost,
  actionRequiresNetworkGrant,
  grantAllowsNetworkHost,
  isMcpCapability,
  MCP_CAPABILITY_PREFIX,
} from "./governance/types.js"
export {
  WECHAT_OUTBOUND_NETWORK_HOSTS,
  WECHAT_OUTBOUND_NETWORK_HOST_SET,
} from "./governance/wechat-network-hosts.js"
export {
  mergeGrantNetworkHosts,
  mcpServerHostnameFromEnv,
  parseGrantNetworkHostsFromEnv,
  resolveGrantNetworkHosts,
  hostnameFromHttpUrl,
} from "./governance/grant-network-hosts.js"
export {
  SANDBOX_PROFILE_NETWORK_ALLOWLIST,
  MAX_NETWORK_ALLOWLIST_ENTRIES,
  DEFAULT_NETWORK_ALLOWLIST_PORT,
  normalizeNetworkAllowlistEntry,
  validateNetworkAllowlist,
  hashNetworkAllowlistForAudit,
  hostnamesFromNetworkAllowlist,
  resolveSandboxNetworkMode,
  isDestinationAllowedInNetworkAllowlist,
  destinationKey,
  envAllowPrivateEgress,
} from "./governance/network-allowlist.js"
