import { describe, expect, it } from "vitest"
import { resolveButlerDbKind } from "./db-kind.js"

describe("resolveButlerDbKind", () => {
  it("defaults to pglite for tests and unset env", () => {
    expect(resolveButlerDbKind({})).toBe("pglite")
    expect(resolveButlerDbKind({ NODE_ENV: "test", DATABASE_URL: "postgres://x" })).toBe("pglite")
  })

  it("uses postgres in production when DATABASE_URL is set", () => {
    expect(
      resolveButlerDbKind({
        NODE_ENV: "production",
        DATABASE_URL: "postgres://butler:butler_dev@127.0.0.1:5432/butler_v5",
      }),
    ).toBe("postgres")
  })

  it("lets BUTLER_V5_DB override", () => {
    expect(
      resolveButlerDbKind({
        NODE_ENV: "production",
        DATABASE_URL: "postgres://x",
        BUTLER_V5_DB: "pglite",
      }),
    ).toBe("pglite")
    expect(resolveButlerDbKind({ BUTLER_V5_DB: "postgres" })).toBe("postgres")
  })
})
