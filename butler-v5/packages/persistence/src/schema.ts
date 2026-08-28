import {
  pgTable,
  text,
  integer,
  boolean,
  timestamp,
  jsonb,
  uuid,
  index,
  uniqueIndex,
  doublePrecision,
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
  projectId: text("project_id"),
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
    /** When true, Child Run may receive a narrowed copy of this grant. Default false. */
    delegable: boolean("delegable").notNull().default(false),
    /** Waiting approval Step that issued this grant; null for Owner-preconfigured grants. */
    approvalId: uuid("approval_id"),
    /** Elevated sandbox profile when Grant lifts provider default isolation. */
    sandboxProfile: text("sandbox_profile"),
    /** host:port egress allowlist when sandboxProfile is network-allowlist (P2b). */
    networkAllowlist: jsonb("network_allowlist").$type<readonly string[] | null>(),
    /** D2.2: first-class capability column (DESIGN §10.3). Source-of-truth mirror of
     * scope->'capabilities'->0; nullable for legacy rows until backfill is verified. */
    capability: text("capability"),
  },
  (t) => ({
    runIdx: index("scoped_grants_run_idx").on(t.runId, t.expiresAt),
    approvalIdx: index("scoped_grants_approval_idx").on(t.approvalId),
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

export const durableMemories = pgTable(
  "durable_memories",
  {
    memoryId: uuid("memory_id").primaryKey().notNull(),
    subject: text("subject").notNull(),
    content: text("content").notNull(),
    sourceKind: text("source_kind").notNull(),
    status: text("status").notNull(),
    confidence: doublePrecision("confidence").notNull(),
    provenance: jsonb("provenance").notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
    confirmedAt: timestamp("confirmed_at", { withTimezone: true }),
  },
  (t) => ({
    subjectStatusIdx: index("durable_memories_subject_status_idx").on(
      t.subject,
      t.status,
      t.updatedAt,
    ),
    expiresIdx: index("durable_memories_expires_idx").on(t.expiresAt),
  }),
)

export const documents = pgTable(
  "documents",
  {
    documentId: uuid("document_id").primaryKey().notNull(),
    subject: text("subject").notNull(),
    title: text("title").notNull(),
    format: text("format").notNull(),
    mimeType: text("mime_type").notNull(),
    byteSize: integer("byte_size").notNull(),
    extractedText: text("extracted_text").notNull(),
    status: text("status").notNull(),
    failureReason: text("failure_reason"),
    provenance: jsonb("provenance").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    subjectUpdatedIdx: index("documents_subject_updated_idx").on(t.subject, t.updatedAt),
  }),
)

export const projectKnowledgeItems = pgTable(
  "project_knowledge_items",
  {
    itemId: uuid("item_id").primaryKey().notNull(),
    projectId: text("project_id").notNull(),
    title: text("title").notNull(),
    kind: text("kind").notNull(),
    body: text("body").notNull(),
    byteSize: integer("byte_size").notNull(),
    provenance: jsonb("provenance").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    projectUpdatedIdx: index("project_knowledge_items_project_updated_idx").on(
      t.projectId,
      t.updatedAt,
    ),
  }),
)

export const procedures = pgTable(
  "procedures",
  {
    procedureId: uuid("procedure_id").primaryKey().notNull(),
    name: text("name").notNull(),
    version: integer("version").notNull(),
    steps: jsonb("steps").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    nameVersionUniq: uniqueIndex("procedures_name_version_uniq").on(t.name, t.version),
  }),
)

export const tasks = pgTable(
  "tasks",
  {
    taskId: uuid("task_id").primaryKey().notNull(),
    subject: text("subject").notNull(),
    title: text("title").notNull(),
    goal: text("goal").notNull(),
    status: text("status").notNull(),
    conversationId: text("conversation_id"),
    procedureId: uuid("procedure_id"),
    procedureStepIndex: integer("procedure_step_index"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
  },
  (t) => ({
    subjectStatusIdx: index("tasks_subject_status_idx").on(t.subject, t.status, t.updatedAt),
  }),
)
