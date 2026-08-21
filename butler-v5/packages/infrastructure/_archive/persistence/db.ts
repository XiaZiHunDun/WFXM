// infrastructure/persistence/db.ts
// 数据库连接 — PostgreSQL via drizzle-orm

import { drizzle } from "drizzle-orm/postgres-js"
import postgres from "postgres"
import { Effect, Layer } from "effect"
import * as schema from "./schema.js"

export class Db extends Effect.Tag("Db")<Db, ReturnType<typeof drizzle<typeof schema>>>() {}

// 从环境变量创建连接
export const DbLive = Layer.effect(
  Db,
  Effect.sync(() => {
    const globalProcess = (globalThis as { process?: { env?: Record<string, string | undefined> } })
      .process
    const url =
      globalProcess?.env?.["DATABASE_URL"] ??
      "postgres://butler:butler_dev@localhost:5432/butler_v5"
    const client = postgres(url, { max: 10 })
    return Db.of(drizzle(client, { schema }))
  }),
)

// 测试用内存数据库
export const makeTestDb = () =>
  Layer.succeed(
    Db,
    // 使用不存在的连接，测试中不会真正查询
    Db.of(drizzle(postgres("postgres://test:test@localhost:5432/test", { max: 1 }), { schema })),
  )
