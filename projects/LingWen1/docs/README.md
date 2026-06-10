# 灵文1号试点文档索引（B4）

> 单一入口，避免散落重复清单。运营主清单在仓库级 [`docs/guides/wechat-daily-smoke-checklist.md`](../../../docs/guides/wechat-daily-smoke-checklist.md)。

| 文档 | 用途 |
|------|------|
| [pilot-setup.md](./pilot-setup.md) | 试点边界、路径、Lead 阶段、发版节奏 |
| [dual-playbook.md](./dual-playbook.md) | **维护态 / 新书态**双剧本 + 微信验收句（B1） |
| [pilot-log.md](./pilot-log.md) | 时间线与验收结论 |
| [memory-guide.md](./memory-guide.md) | 记忆写入边界、O1–O6 运维 |
| [project-lead-scope.md](./project-lead-scope.md) | 厂长五条能力、禁止项 |
| [lead-phase1-check.md](./lead-phase1-check.md) | Lead 阶段 1 检查 |
| [workflow-output.md](./workflow-output.md) | 工作流输出约定 |
| [wechat-smoke.md](./wechat-smoke.md) | 运行时生成的验收文件（非手册） |

**仓库级关联**：

| 文档 | 用途 |
|------|------|
| [phase4-ops-runbook.md](../../../docs/guides/phase4-ops-runbook.md) | Phase 4 A+B 总 runbook |
| [runtime-ops.md](../../../docs/guides/runtime-ops.md) | systemd timer、推送队列 |
| [memory-ops.md](../../../docs/guides/memory-ops.md) | 记忆 reindex、env |
| [cost-calibration.md](../../../docs/guides/cost-calibration.md) | A5 成本标定 |

**脚本**：

```bash
bash scripts/butler-phase4-smoke.sh          # Phase 4 自动化守门
bash scripts/butler-lingwen-lead-smoke.sh    # Lead 白名单
bash scripts/sync-lingwen-project-skills.sh  # 同步 Skill 到 .butler/skills
```
