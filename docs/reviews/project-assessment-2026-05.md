# WFXM / Butler 项目评估（2026-05）

> **结论**：平台约 **4/5** 成熟度；灵文1号试点 **可运营**；整理 P0–P2 已完成。  
> **后续**：[`plans/post-consolidation-roadmap-2026-05.md`](../plans/post-consolidation-roadmap-2026-05.md)

---

## 1. 评分摘要

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构清晰度 | ★★★★☆ | v4 单栈；Hermes 已解耦；三层模型（项目/通道/主机工具）已文档化 |
| 微信主场景 | ★★★★☆ | 八步剧本、记忆 M1–M4、Lead、runtime 已真机验收 |
| 可测试性 | ★★★★☆ | 1093 pytest + 分层 `butler-smoke.sh` + pre-release 9 步 |
| 多项目就绪 | ★★★☆☆ | DemoPilot 已有；Git 登记与第二 Lead 项目待打磨 |
| 文档一致性 | ★★★★☆ | P0–P2 后脉络清晰；历史在 `docs/history/` |
| 运维可重复 | ★★★★☆ | systemd、timer、ops-bundle、gateway-ops 脚本齐全 |

---

## 2. 已交付亮点

- **项目层**：`project.yaml`（`pack` / `lifecycle` / `lead`）、preflight、微信 `/项目 新建|体检`
- **Lead**：灵文厂长 Loop、工具白名单、`butler-lingwen-lead-smoke.sh`
- **记忆**：本地向量 + FTS hybrid、围栏、queue_prefetch、微信待审
- **Runtime**：`jobs.yaml`、批准链、推送队列与 drain
- **整理**：依赖瘦身、v3 测试移除、v1 迁 tag、设计文档拆分

---

## 3. 主要缺口（非阻塞）

| 缺口 | 建议轨道 |
|------|----------|
| 媒体真机（图/语音）未全勾 | A2 |
| mutating 发布未做真机批准演练 | A3 |
| 多项目 Git 登记无第二真实 repo 试点 | C1 |
| `config.yaml` 稳定项仍以 env 为主（P2.4 仅文档） | D1 |
| 灵文「新书态」仅 Skill 有述，试点文档可加强 | B1 |

---

## 4. 边界（维持不变）

- **`reference/`**：主公维护的外部对照，不参与 Butler 发版与整理自动化。
- **`novel-factory/`**：领域生产由脚本 + `workflow_state.json` 驱动；Butler 读状态、派工、runtime，不替代 25 步主流程。

---

## 5. 度量（2026-05-22）

| 指标 | 值 |
|------|-----|
| pytest | 1093 passed，1 skipped，18 deselected |
| pre-release smoke | 9 步全绿 |
| 灵文试点结论 | 通过，可运营 |
