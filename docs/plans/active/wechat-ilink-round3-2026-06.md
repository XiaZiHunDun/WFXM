# wechat_ilink 第三轮拆分（ENG-13）— 范围与验收

> **状态**：**done**（2026-06-29）· PR-1～PR-3 完成 · **非**发版硬门槛  
> **登记**：[`roadmap-backlog` §3.12](../decisions/roadmap-backlog-and-boundaries-2026-05.md#312-条件触发工程债-2026-06)  
> **前置**：ENG-5 ✅（`connect_phases` / `poll_phases` / `send_phases` / `qr_phases`）；`phases.py` 门面 ~370 行  
> **原则**：零行为变更；只薄化 `WeChatAdapter` 宿主；真机 smoke 为最终验收

---

## 1. 何时立项（触发条件）

满足 **任一** 即建议排期 ENG-13：

| # | 触发 |
|---|------|
| T1 | 计划改 iLink 协议 / 登录 / 长轮询 / CDN 上传 / 出站附件链 |
| T2 | `wechat_ilink/__init__.py` 单次 PR 改动 >150 行且 review 困难 |
| T3 | 出站/登录类生产事故需高频迭代 `WeChatAdapter` |
| T4 | 新人 onboarding 微信网关域超过 2 天仍无法定位改动点 |

**不触发则不做**：发版、Loop、工具、记忆改动与 `__init__.py` 无关时，维持现状。

---

## 2. 现状基线（2026-06-29）

| 路径 | 行数 | 说明 |
|------|------|------|
| `gateway/platforms/wechat_ilink/__init__.py` | **~46** | PR-3 收口（re-export + 薄 wrapper） |
| `gateway/platforms/wechat_ilink/adapter.py` | ~360 | `WeChatAdapter` 类壳 + 委托 |
| `adapter_lifecycle.py` / `adapter_inbound.py` / `adapter_outbound.py` / `adapter_media.py` | 已存在 | ENG-13 职责拆分 |

守门：`tests/gateway/test_wechat_ilink_split.py`（R1-4a/b 契约 + 行数上限）

---

## 3. 范围

### 3.1 做

| 项 | 交付 |
|----|------|
| **薄化 `WeChatAdapter`** | 公共方法保持签名；实现迁到子模块 |
| **建议子模块**（按职责，名称可微调） | |
| → `adapter_lifecycle.py` | `connect` / `disconnect` / `run` 薄编排（调用既有 phases） |
| → `adapter_inbound.py` | 入站轮询、dedup、chat-policy（若仍在 `__init__`） |
| → `adapter_outbound.py` | `send` / `send_file` / typing / ack 薄编排 |
| → `adapter_media.py` | 媒体下载 / CDN / 附件路径（若块 >80 行） |
| **`__init__.py`** | 仅 re-export `WeChatAdapter`、registry shim、模块 docstring |
| **契约测试** | 扩展 `test_wechat_ilink_split.py`：新方法行数 <50、公开 API 不删 |

### 3.2 不做

| 不做 | 原因 |
|------|------|
| 改 iLink HTTP 语义 / 加密 / 字段 | 非重构范围；另立协议 PR |
| 重写 `phases.py` 或合并子 phase 文件 | ENG-5 已收口 |
| 改 `message_handler` / `outbound_bridge` 行为 | 正交层 |
| 顺带「优化」并发 / 缓存策略 | 行为变更须单独立项 |
| 真机依赖的新功能 | 先拆后做 feature |

---

## 4. 验收标准

1. **零行为变更**：`butler-pytest-fast-gate.sh` 绿（含 `butler-wechat-attach-probe.sh`、`butler-cc-harness-gate.sh`）。
2. **Gateway 域**：`bash scripts/butler-domain-pytest.sh gateway` 绿。
3. **拆分契约**：`PYTHONPATH=. pytest tests/gateway/test_wechat_ilink_split.py -q` 绿；`WeChatAdapter` 上帝方法均 <50 行（与 R1-4a 一致）。
4. **体量**：`wechat_ilink/__init__.py` **<400 行**（re-export + 类壳）。
5. **真机**（有环境时）：`docs/guides/wechat-daily-smoke-checklist.md` 出站 + 登录项各勾 1 次；或 `pilot-log` 登记暂缓原因。
6. **复杂度报告**：`bash scripts/butler-complexity-report.sh` 无新增 >600 行单文件。

---

## 5. 建议 PR 切分

```text
PR-1  adapter_lifecycle + adapter_inbound（只迁方法，不改逻辑）
PR-2  adapter_outbound + adapter_media
PR-3  __init__.py 收口 + test_wechat_ilink_split 更新
```

每 PR 后跑：`butler-domain-pytest.sh gateway` + `test_wechat_ilink_split.py`。

---

## 6. 守门命令（发版 SSOT）

```bash
bash scripts/butler-pytest-fast-gate.sh
bash scripts/butler-domain-pytest.sh gateway
PYTHONPATH=. pytest tests/gateway/test_wechat_ilink_split.py -q
bash scripts/butler-wechat-attach-probe.sh
```

---

## 7. 相关（勿混立项）

| 文档 | 关系 |
|------|------|
| [`software-engineering-refactor-2026-06.md`](software-engineering-refactor-2026-06.md) §2.G | 条件触发工程债总表 |
| [`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md) D8 | 识图 P3 — **产品**，非本拆分 |
| PROD-P2-01 | 第一轮子包 — **done** |

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-29 | PR-3：`__init__.py` <50 行；`adapter.py` + `adapter_lifecycle.py` + `_compat.py` + `qr_login.py` |
| 2026-06-29 | PR-2：`adapter_outbound.py` + `adapter_media.py`（出站/typing/媒体下载） |
| 2026-06-29 | PR-1：`adapter_inbound.py`（poll 分发 + 入站 process_message） |
| 2026-06-29 | 初稿：ENG-13 条件触发范围 + 验收 + PR 切分 |
