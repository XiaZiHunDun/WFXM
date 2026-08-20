import { mkdtempSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { upsertWechatEnvFile } from "./env-file.js"

describe("upsertWechatEnvFile", () => {
  it("replaces token keys without dropping unrelated env", () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-v5-env-"))
    const path = join(dir, "env")
    upsertWechatEnvFile(path, {
      token: "old-token",
      accountId: "old-id",
      baseUrl: "https://ilinkai.weixin.qq.com",
    })
    upsertWechatEnvFile(path, {
      token: "new-token",
      accountId: "new-id",
      baseUrl: "https://ilinkai.weixin.qq.com",
    })
    const text = readFileSync(path, "utf8")
    expect(text).toContain("WECHAT_TOKEN=new-token")
    expect(text).not.toContain("old-token")
    expect(text).toContain("BUTLER_V5_ILINK_ENABLED=1")
  })
})
