# 微信真机签收矩阵（2026-07）

> **用途**：同一话术在真机清单、handler-sim、corpus 三处的对应关系；避免「sim 绿但真机半年未点」。  
> **真机 SSOT**：[`wechat-daily-smoke-checklist.md`](./wechat-daily-smoke-checklist.md)  
> **自动化 SSOT**：`.butler/simulation/wechat-owner-scenarios.yaml` + `tests/corpus/suites/wechat_real/lw_real/`

## 图例

| 列 | 含义 |
|----|------|
| 真机 | `wechat-daily-smoke-checklist.md` 中的 ID |
| Sim | `butler-wechat-owner-sim.sh --track …` |
| Corpus | `MT-*` 多轮 / `PROD-*` 单轮 |
| 真机日期 | pilot-log 或清单勾选日期；`—` = 待勾 |

## 核心路径（已验 ☑）

| 话术摘要 | 真机 | Sim track | Corpus | 真机日期 |
|----------|------|-----------|--------|----------|
| `/状态` 当前项目 | 0 | core | REAL-* / PROD | 2026-05-21 ☑ |
| 读 README 摘要 | 3 | core | MT-19 | 2026-05-21 ☑ |
| 委派写 wechat-smoke | 4 | delegate | MT-05 / PROD | 2026-05-21 ☑ |
| `/新对话` + 不复述 | 6–6b | memory | MT-04 / MT-28 | 2026-05-21 ☑ |
| 记忆 M1–M4 | M1–M4 | memory | utterance_catalog | 2026-05-22 ☑ |
| 入站图/语音 | M-img/voice | — | inbound pytest | 2026-06-10 ☑ |

## 线束 H 区（待验 ☐）

| 话术摘要 | 真机 | Sim | Corpus | 真机日期 |
|----------|------|-----|--------|----------|
| `/诊断` 含 hooks/用量 | H1 | owner-ux | PROD-034 | — |
| `/计划` → `/状态` 规划模式 | H2–H3 | owner-daily ✅ | MT-36 / PROD-031 | sim 2026-07-08 |
| 委派 progress + 双推送 | H4–H6 | delegate | completion_notify pytest | — |
| `/任务` 列表 | H7 | slash | PROD-032 | — |
| 长任务中插队 | H11 | — | MT-30 | — |
| `/简报` 四块 | H12 | owner-daily ✅ | MT-35 / PROD-045 | sim 2026-07-08 |
| onboarding 欢迎 | H13 | — | — | — |

## Owner 日常扩展（2026-07 新增）

| 话术摘要 | 真机 | Sim | Corpus | 真机日期 |
|----------|------|-----|--------|----------|
| `/新会话` 别名 | H-NEW1 | owner-daily ✅ | MT-29 / PROD-036 | sim 2026-07-08 |
| `/反馈` 硬反馈 | H-OT2 | owner-daily ✅ | MT-31 / PROD-037 | sim 2026-07-08 |
| 含糊删 smoke 文件 | OWN-01 | — | MT-26 / PROD-038 | — |
| 跨项目问灵文进度 | OWN-02 | — | MT-27 / PROD-040 | — |
| 闲聊 + 只读 | OWN-03 | — | MT-33 | — |
| 连发「在吗」「看下状态」 | OWN-04 | owner-daily | MT-32 / PROD-041 | — |
| 工作流口语链 | OWN-05 | owner-daily | MT-24 / PROD-043 | — |
| novel-factory 进度 | OWN-06 | — | MT-25 | — |
| 删除失败改只读 | — | — | MT-34 / PROD-039 | — |
| 技术栈 facts M5 | MEM-M5 | memory-ext ✅ | MT-37 / PROD-044 | sim 2026-07-08 |
| `/新对话` 不复述 M6 | MEM-M6 | memory-ext ✅ | MT-28 | sim 2026-07-08 |
| 记忆批准闭环 M7 | MEM-M7 | memory-ext ✅ | MT-23 | sim 2026-07-08 |

## 推荐执行顺序（真机 ~30 分钟）

1. `bash scripts/butler-wechat-owner-sim.sh --track owner-daily,memory-ext`（本地预演）
2. 微信按清单 **Owner 日常扩展** + 勾选 **H1–H3、H12**（无委派时可跳过 H4–H6）
3. 更新 [`projects/LingWen1/docs/pilot-log.md`](../../projects/LingWen1/docs/pilot-log.md) 与本表「真机日期」列

## 语料运营

新增真机话术脱敏后：

```bash
python3 scripts/corpus/append_production.py --user "…" --kind llm --script … --expect-json '…'
# 或多轮：编辑 utterance_multiturn_catalog.yaml → pytest tests/corpus/runners/test_gateway_multiturn_catalog.py -q
```

见 [`docs/plans/corpus/wechat-corpus-ops-2026-05.md`](../plans/corpus/wechat-corpus-ops-2026-05.md)。
