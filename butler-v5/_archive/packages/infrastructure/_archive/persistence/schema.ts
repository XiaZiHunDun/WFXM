// infrastructure/persistence/schema.ts
// Drizzle ORM 表定义 — 4 张表（events + outbox + intent_receipts + load_bearing_marks）

import { pgTable, text, integer, timestamp, jsonb, boolean } from "drizzle-orm/pg-core"

// ─── 事件流（Event Sourcing 写模型 + 审计） ─────────────
export const events = pgTable("events", {
  id: text("id").primaryKey(),
  streamId: text("stream_id").notNull(),
  version: integer("version").notNull(),
  type: text("type").notNull(),
  payload: jsonb("payload").notNull(),
  createdAt: timestamp("created_at").notNull().defaultNow(),
})

// ─── 出站消息（Outbox Pattern，双写一致性） ──────────────
export const outbox = pgTable("outbox", {
  id: text("id").primaryKey(),
  aggregateId: text("aggregate_id").notNull(),
  type: text("type").notNull(),
  payload: jsonb("payload").notNull(),
  publishedAt: timestamp("published_at"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
})

// ─── IntentReceipts 表 [G-1] ───────────────────────────
export const intentReceipts = pgTable("intent_receipts", {
  id: text("id").primaryKey(),
  intent: text("intent").notNull(),
  evidenceFiles: jsonb("evidence_files").notNull(),
  locDelta: jsonb("loc_delta").notNull(),
  chainCompleteness: integer("chain_completeness").notNull(),
  guardFindings: jsonb("guard_findings").notNull(),
  authorAgent: text("author_agent").notNull(),
  reviewerAgent: text("reviewer_agent"),
  ownerApprovalSig: text("owner_approval_sig"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
})

// ─── 承重代码标记表 [G-2] ──────────────────────────────
export const loadBearingMarks = pgTable("load_bearing_marks", {
  path: text("path").primaryKey(),
  reason: text("reason").notNull(),
  markedBy: text("marked_by").notNull(),
  ownerApproved: boolean("owner_approved").notNull().default(false),
  alternatives: jsonb("alternatives"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
})
