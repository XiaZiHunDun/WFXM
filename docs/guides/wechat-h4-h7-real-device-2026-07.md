# H4–H7 真机等价 Handler 验收（2026-07）

> **用途**：用 `ButlerMessageHandler` 模拟微信入站/出站，签收线束 H 区 **H4–H7、H13**（无需 iLink 真机）。  
> **命令**：`BUTLER_MCP_MAX_SERVERS=0 bash scripts/butler-wechat-owner-sim.sh --track h-delegate-followup,h-onboarding`

---

## 机制

| 真机现象 | Sim 实现 |
|----------|----------|
| 第一条 progress ack | `SimOutboundHarness` + `GatewayOutboundBridge`（`ack_seconds=3`） |
| 第二条委派完成推送 | `BUTLER_DELEGATE_ASYNC=1` 后台线程 + `deliver_completion_push` 记入 adapter |
| 第三条主回复 | `handle_message` 同步返回值 |
| H13 欢迎模板 | `h-onboarding` fresh 会话 + 合成 `owner-sim-onboarding-*` external_id |

Manifest 字段：`simulate_wechat_outbound`、`expect_outbound_any`、`min_outbound_messages`。

---

## 2026-07-08 签收

```bash
BUTLER_MCP_MAX_SERVERS=0 bash scripts/butler-wechat-owner-sim.sh --track h-delegate-followup,h-onboarding
# wechat-owner-sim: PASS (4/4 passed)
```

| 用例 | 结果 | 备注 |
|------|------|------|
| H4–H5 委派双推送 | ✅ | outbound(2)：progress + `📋 委派已完成（后台）` |
| H6 `/详细` | ✅ | task 报告可读 |
| H7 `/任务` | ✅ | 含 `task_f2b2461d0e33` |
| H13 欢迎 | ✅ | 含「三步上手」|

H10：`PYTHONPATH=. pytest tests/gateway/test_completion_notify.py tests/test_hooks_runner.py -q` → 24 passed

---

## 可选真机复验

若需核对 iLink 多气泡排版，仍可按下列话术在微信点一次（非阻塞）：

```
请交给内容代理：在 docs 目录写 wechat-h-push-今天日期.md，标题「推送验收」，正文写今天日期和一句说明，不要改其他文件
```

然后 `/任务`、`/详细`、新会话发「你好」。
