import {
  pgTable,
  text,
  integer,
  timestamp,
  jsonb,
  uuid,
  index,
  uniqueIndex,
} from "drizzle-orm/pg-core"

export const eventStore = pgTable(
  "event_store",
  {
    eventId: uuid("event_id").primaryKey().notNull(),
    streamId: text("stream_id").notNull(),
    streamType: text("stream_type").notNull(),
    streamVersion: integer("stream_version").notNull(),
    eventType: text("event_type").notNull(),
    eventVersion: integer("event_version").notNull(),
    payload: jsonb("payload").notNull(),
    occurredAt: timestamp("occurred_at", { withTimezone: true }).notNull(),
    causationId: text("causation_id"),
    correlationId: text("correlation_id").notNull(),
    actorKind: text("actor_kind").notNull(),
    actorId: text("actor_id").notNull(),
  },
  (t) => ({
    streamIdx: index("event_store_stream_idx").on(t.streamId, t.streamVersion),
    streamUniq: uniqueIndex("event_store_stream_uniq").on(t.streamId, t.streamVersion),
  }),
)

export const outbox = pgTable(
  "outbox",
  {
    messageId: uuid("message_id").primaryKey().notNull(),
    streamId: text("stream_id").notNull(),
    aggregateType: text("aggregate_type").notNull(),
    payload: jsonb("payload").notNull(),
    status: text("status").notNull(),
    attemptCount: integer("attempt_count").notNull().default(0),
    nextAttemptAt: timestamp("next_attempt_at", { withTimezone: true }).notNull(),
    leaseOwner: text("lease_owner"),
    leaseUntil: timestamp("lease_until", { withTimezone: true }),
    lastError: text("last_error"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    deliveredAt: timestamp("delivered_at", { withTimezone: true }),
  },
  (t) => ({
    statusIdx: index("outbox_status_idx").on(t.status, t.nextAttemptAt),
    leaseIdx: index("outbox_lease_idx").on(t.leaseUntil),
  }),
)

export const snapshots = pgTable("snapshots", {
  streamId: text("stream_id").primaryKey().notNull(),
  streamVersion: integer("stream_version").notNull(),
  payload: jsonb("payload").notNull(),
  takenAt: timestamp("taken_at", { withTimezone: true }).notNull(),
})

export const projections = pgTable("projections", {
  projectionName: text("projection_name").primaryKey().notNull(),
  version: integer("version").notNull(),
  state: jsonb("state").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
})

export const conversations = pgTable("conversations", {
  conversationId: text("conversation_id").primaryKey().notNull(),
  subject: text("subject").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
})

export const messages = pgTable(
  "messages",
  {
    messageId: uuid("message_id").primaryKey().notNull(),
    conversationId: text("conversation_id")
      .notNull()
      .references(() => conversations.conversationId),
    role: text("role").notNull(),
    content: jsonb("content").notNull(),
    triggerSource: text("trigger_source"),
    idempotencyKey: text("idempotency_key"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    conversationIdx: index("messages_conversation_idx").on(t.conversationId, t.createdAt),
    idempotencyUniq: uniqueIndex("messages_idempotency_uniq").on(t.idempotencyKey),
  }),
)

export const runs = pgTable(
  "runs",
  {
    runId: uuid("run_id").primaryKey().notNull(),
    conversationId: text("conversation_id")
      .notNull()
      .references(() => conversations.conversationId),
    parentRunId: uuid("parent_run_id"),
    triggerSource: text("trigger_source").notNull(),
    idempotencyKey: text("idempotency_key").notNull(),
    subject: text("subject").notNull(),
    goal: text("goal").notNull(),
    status: text("status").notNull(),
    budget: jsonb("budget").notNull(),
    deadline: timestamp("deadline", { withTimezone: true }),
    version: integer("version").notNull().default(1),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    idempotencyUniq: uniqueIndex("runs_idempotency_uniq").on(t.idempotencyKey),
    conversationIdx: index("runs_conversation_idx").on(t.conversationId, t.createdAt),
  }),
)

export const steps = pgTable(
  "steps",
  {
    stepId: uuid("step_id").primaryKey().notNull(),
    runId: uuid("run_id")
      .notNull()
      .references(() => runs.runId),
    kind: text("kind").notNull(),
    status: text("status").notNull(),
    input: jsonb("input").notNull(),
    output: jsonb("output"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    runIdx: index("steps_run_idx").on(t.runId, t.createdAt),
  }),
)

export const scopedGrants = pgTable(
  "scoped_grants",
  {
    grantId: uuid("grant_id").primaryKey().notNull(),
    runId: uuid("run_id")
      .notNull()
      .references(() => runs.runId),
    subject: text("subject").notNull(),
    scope: jsonb("scope").notNull(),
    remainingUses: integer("remaining_uses"),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    runIdx: index("scoped_grants_run_idx").on(t.runId, t.expiresAt),
  }),
)

export const auditEvents = pgTable(
  "audit_events",
  {
    auditId: uuid("audit_id").primaryKey().notNull(),
    runId: uuid("run_id"),
    conversationId: text("conversation_id"),
    action: text("action").notNull(),
    subject: text("subject").notNull(),
    detail: jsonb("detail").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    conversationIdx: index("audit_events_conversation_idx").on(t.conversationId, t.createdAt),
    runIdx: index("audit_events_run_idx").on(t.runId, t.createdAt),
  }),
)
