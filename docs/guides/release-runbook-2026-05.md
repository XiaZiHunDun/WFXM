# Butler 发版 Runbook（一条链）

> **更新**：2026-05-25 | 个人微信网关主场景  
> 细节展开：链到专文，本文只保留顺序与命令。

---

## 1. 发版前（本机）

| 步 | 命令 / 文档 | 通过标准 |
|----|-------------|----------|
| 1 | `bash scripts/butler-gateway-ops.sh preflight` | 无 FAIL |
| 2 | `butler doctor` | 无关键 WARN（见 [wechat-gateway-ops](./wechat-gateway-ops.md)） |
| 3 | `bash scripts/butler-pre-release-smoke.sh` | 输出 `ALL PASSED`（含 step 12 **strict handler** warn-only；发版前可单独跑 `bash scripts/butler-web-search-route-sim.sh --handler --strict-handler` 作硬验收） |
| 4 | 改 gateway / 语料时：`./scripts/corpus-test.sh pr-gate` | 见 [CONTRIBUTING.md](../../CONTRIBUTING.md) |
| 5 | 改五报告 P5–P10：`./scripts/butler-five-reports-gate.sh` | 退出 0 |
| 6 | `bash scripts/butler-pre-release-smoke.sh` 含 **B9 oracle Tier-1**（`butler-b9-release-gate.sh`） | 退出 0 |

pytest 基线：[`tests/README.md`](../../tests/README.md)（`PYTHONPATH=. pytest -q`）。

**B9 LIVE 周循环**（防回退，需 API）：`bash scripts/butler-b9-weekly-learning.sh` 或 `bash scripts/butler-eval-weekly.sh`。

---

## 2. 部署网关

```bash
cd ~/projects/WFXM
bash scripts/install-butler-gateway-service.sh   # 首次或单元变更
bash scripts/butler-gateway-ops.sh upgrade         # 常规：pull + 重装单元 + 重启
bash scripts/butler-gateway-ops.sh status
```

运维全文：[wechat-gateway-ops.md](./wechat-gateway-ops.md)

---

## 3. 发版后（真机）

| 步 | 文档 | 说明 |
|----|------|------|
| 1 | [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) | H1–H10，约 15–25 分钟 |
| 2 | [wechat-core-scenario.md](./wechat-core-scenario.md) | 八步剧本（按需加深） |

试点项目：**灵文1号**（`projects/LingWen1/`）。

---

## 4. 失败时

| 现象 | 先看 |
|------|------|
| 网关无响应 | `butler-gateway-ops.sh logs` · preflight · `.env` |
| 测试红 | `tests/README.md` 分层；缩小到相关 `tests/test_*` |
| 语料 PR 红 | `docs/plans/corpus/corpus-testing-module-design-2026-05.md` |
| 诊断异常 | [diagnostic-thresholds.md](../ops/diagnostic-thresholds.md) · 微信 `/诊断` |

---

## 5. 相关索引

- 产品后续规划：[`post-consolidation-roadmap`](../plans/active/post-consolidation-roadmap-2026-05.md)
- 能力 env 总表：[`capabilities-index-2026-05.md`](./capabilities-index-2026-05.md)
