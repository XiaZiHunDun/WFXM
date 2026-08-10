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
