# Phase 5 — O9 LLM 基准 + 多项目（C）

> 真机验收统一放在全计划完善后；本阶段以自动化守门为主。

---

## 一键守门

```bash
bash scripts/butler-phase5-smoke.sh
```

---

## O9 · B9 LLM 端到端基准

| 模式 | 命令 | 说明 |
|------|------|------|
| **oracle**（CI 默认） | `bash scripts/butler-eval-llm-benchmark.sh` | 验证 B9 任务 spec + verify 钩子 |
| **live** | `BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-llm-benchmark.sh` | 真实 `delegate_task` + MiniMax |

任务：

| ID | 描述 |
|----|------|
| `B9_fix_greet` | 修 hello.py 返回值 |
| `B9_create_marker` | 创建 `b9_marker.txt` |

LangFuse 评分名：`llm_benchmark.*`（`eval_bridge.llm_benchmark_to_scores`）

环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EVAL_LLM_BENCHMARK` | `0` | `1` = live delegate 模式 |

---

## 轨道 C — 多项目

### C1 · Git 登记

```bash
butler project register https://github.com/user/repo.git --name "外部仓库"
```

微信：`/项目 register 外部仓库 https://github.com/user/repo.git`

### C2 · 默认项目策略

见 [`default-project-policy.md`](./default-project-policy.md)。`/诊断` 含 **默认项目策略** 块。

### C3 · 多 Lead 项目

| 项目 | Lead | Skill |
|------|------|-------|
| 灵文1号 | `lead: true` | `lingwen-project-lead.md` |
| 演示试点 | `lead: true` | `demo-project-lead.md` |

```bash
bash scripts/sync-project-skills.sh LingWen1
bash scripts/sync-project-skills.sh DemoPilot
bash scripts/butler-lingwen-lead-smoke.sh
bash scripts/butler-demo-lead-smoke.sh
```

### C4 · 新建 + pack 模板

```bash
butler create MyApp --name "我的应用" --template software-default
butler create Novel --template novel-factory --pack novel-factory
```

微信：`/项目 新建 MyApp knowledge-light`

模板：`software-default` | `novel-factory` | `knowledge-light`

---

## 完成标准（自动化）

| ID | 条件 |
|----|------|
| O9 | `butler-eval-llm-benchmark.sh` oracle 全绿 |
| C1 | register Git URL CLI + 微信 clone 单测 |
| C2 | `/诊断` 含默认项目策略 |
| C3 | 双 Lead smoke 通过 |
| C4 | create 模板单测 + 微信用法提示 |

完成后进入后续规划（D2-4/D2-5 度量采集等，按需）。
