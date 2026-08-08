// domain/conversation/context.ts
// 上下文窗口管理 — 纯函数

import type { ContextWindow } from "./types.js"

export function chooseStrategy(window: ContextWindow): "summarize" | "truncate" {
  if (window.tokens > window.maxTokens * 0.9) return "summarize"
  if (window.tokens > window.maxTokens * 0.7) return "truncate"
  return "summarize"
}

export function makeContextWindow(tokens: number, maxTokens: number): ContextWindow {
  return { tokens, maxTokens, compressed: false }
}

export function isNearLimit(window: ContextWindow, threshold = 0.85): boolean {
  return window.tokens > window.maxTokens * threshold
}
