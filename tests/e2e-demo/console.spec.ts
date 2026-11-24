import { expect, test, type Page } from "@playwright/test"

/**
 * Demo 控制台交互 E2E：
 *   1. 页面可加载
 *   2. 发送消息 → 脚本化回复
 *   3. 第二轮触发 write_file 审批 → 批准且待审批清空
 *   4. 拒绝路径 → 待审批清空
 *   5. 重置会话 → 消息与审批清空
 *
 * 每个用例前通过界面「重置会话」重建 demo app，保证 fixture 从第一条开始回放。
 */

async function send(page: Page, content: string): Promise<void> {
  await page.getByTestId("input").fill(content)
  await page.getByTestId("send").click()
  await expect(page.getByTestId("bubble-user").last()).toContainText(content)
  // 请求结束（无论成功/失败）后 send 按钮恢复可用。
  await expect(page.getByTestId("send")).toBeEnabled()
}

test.describe("Butler v5 demo console", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/")
    await expect(page.getByRole("heading", { name: "Butler v5 Demo Console" })).toBeVisible()
    await expect(page.getByTestId("input")).toBeEditable()
    await page.getByTestId("reset").click()
    await expect(page.getByTestId("status")).toHaveText("会话已重置")
    await expect(page.getByTestId("approval-empty")).toBeVisible()
  })

  test("发送消息后收到脚本化回复", async ({ page }) => {
    await send(page, "你好")
    await expect(page.getByTestId("bubble-bot").last()).toContainText("脚本化")
    await expect(page.getByTestId("status")).toHaveText("就绪")
    await expect(page.getByTestId("pending-count")).toHaveText("0")
  })

  test("触发审批并批准后清空待审批", async ({ page }) => {
    await send(page, "你好")
    await expect(page.getByTestId("status")).toHaveText("就绪")

    await send(page, "帮我写个文件")
    await expect(page.getByTestId("status")).toHaveText("等待审批")

    const item = page.getByTestId("approval-item")
    await expect(item).toHaveCount(1)
    await expect(item).toContainText("write_file")
    await expect(page.getByTestId("pending-count")).toHaveText("1")

    await item.getByRole("button", { name: "批准" }).click()
    await expect(page.getByTestId("approval-item")).toHaveCount(0)
    await expect(page.getByTestId("pending-count")).toHaveText("0")
    await expect(page.getByTestId("status")).toHaveText("已批准")
    await expect(page.getByTestId("bubble-bot").last()).toContainText("已批准")
  })

  test("拒绝后审批项消失", async ({ page }) => {
    await send(page, "你好")
    await send(page, "帮我写个文件")

    const item = page.getByTestId("approval-item")
    await expect(item).toHaveCount(1)
    await item.getByRole("button", { name: "拒绝" }).click()

    await expect(page.getByTestId("approval-item")).toHaveCount(0)
    await expect(page.getByTestId("status")).toHaveText("已拒绝")
    await expect(page.getByTestId("bubble-bot").last()).toContainText("已拒绝")
  })

  test("聊天框文字「确认」完成审批", async ({ page }) => {
    await send(page, "你好")
    await expect(page.getByTestId("status")).toHaveText("就绪")

    await send(page, "帮我写个文件")
    await expect(page.getByTestId("status")).toHaveText("等待审批")
    await expect(page.getByTestId("approval-item")).toHaveCount(1)

    // 真机微信里 owner 直接回「确认」；控制台聊天框必须走同一条 inline approval。
    await send(page, "确认")
    await expect(page.getByTestId("approval-item")).toHaveCount(0)
    await expect(page.getByTestId("pending-count")).toHaveText("0")
    await expect(page.getByTestId("status")).toHaveText("就绪")
    await expect(page.getByTestId("bubble-bot").last()).toContainText("wrote demo-note.txt")
  })

  test("重置会话清空消息与待审批", async ({ page }) => {
    await send(page, "你好")
    await expect(page.getByTestId("bubble-user")).toHaveCount(1)

    await page.getByTestId("reset").click()
    await expect(page.getByTestId("status")).toHaveText("会话已重置")
    await expect(page.getByTestId("bubble-user")).toHaveCount(0)
    await expect(page.getByTestId("bubble-bot")).toHaveCount(0)
    await expect(page.getByTestId("pending-count")).toHaveText("0")
    await expect(page.getByTestId("approval-empty")).toBeVisible()
  })
})
