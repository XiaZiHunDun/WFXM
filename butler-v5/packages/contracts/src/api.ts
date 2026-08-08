import type { ToolName } from "../../domain/src/tools/types.js"

export type ApiVersion = "v1"

export interface StartConversationRequest {
  readonly apiVersion: ApiVersion
  readonly projectId: string
  readonly toolName: ToolName | null
  readonly content: string
}

export interface StartConversationResponse {
  readonly conversationId: string
  readonly turnId: string
}

export type ApiResult<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly code: string; readonly message: string }
