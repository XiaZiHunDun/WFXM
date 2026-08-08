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
