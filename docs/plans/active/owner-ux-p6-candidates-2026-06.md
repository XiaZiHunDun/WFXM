# PROD-P6 — 运营期抛光（2026-06）

> **状态**：立项 **2026-06-22** · **P6-A ✅ 2026-06-26**（onboard CLI + 出站诊断 + 运维节奏脚本）  
> **登记**：[`roadmap-backlog` §3.10](../decisions/roadmap-backlog-and-boundaries-2026-05.md#310-运营期抛光-p6--2026-06)  
> **前置**：PROD-P0～P5 ✅ · EXT-5 ✅ · G1-04 观测窗 **06-09→07-31**  
> **原则**：与 G1-04 观测并行；小批可验收；不重复 §1 否决

---

## 0. 背景

P0–P5 已收束核心能力与真机 UX 债。下一阶段以 **运营观测 + 安装/onboard 减负 + 故障自助** 为主，工程债（pytest 全量、model_resolve）穿插小 PR。

---

## 1. 立项表

| ID | 名称 | 批次 | 优先级 | 状态 |
|----|------|------|--------|------|
| PROD-P6-01 | `butler onboard` 一页纸向导 | P6-A | P0 | **done** 2026-06-26 |
| PROD-P6-02 | `/诊断` 出站失败人话行 | P6-A | P0 | **done** 2026-06-26 |
| PROD-P6-03 | 运维节奏脚本 `butler-ops-cadence.sh` | P6-A | P0 | **done** 2026-06-26 |
| PROD-P6-04 | G1-04 窗满结案 + gap register | P6-B | P0 | **backlog**（→07-31） |
| PROD-P6-05 | Owner PMF 复盘（P4-08 数据） | P6-B | P1 | **backlog**（窗满后） |
| PROD-P6-06 | pytest 全量泄漏逐模块修 | P6-C | P2 | **backlog** |
| PROD-P6-07 | `model_resolve` 单路径收敛 | P6-C | P2 | **backlog** |

**建议顺序**：P6-A（本周）→ 窗内每周 G1-04 打卡 → 07-31 后 P6-B → P6-C 穿插。

---

## 2. PROD-P6-01 · `butler onboard`

### 问题

T0 安装阶段 env 项多，运维与 Owner 角色易混淆；`deploy-profiles` 文档已有但缺 CLI 入口。

### 范围

| 做 | 不做 |
|----|------|
| `butler onboard [--profile gateway\|dev-local\|dev-remote]` 打印剖面清单 + 下一步 | GUI 安装向导 |
| 链 `deploy-profiles` · `owner-first-week` · `wechat-gateway-ops` | 删减 reference.md |

### 验收

1. `butler onboard` exit 0；输出含剖面名、必填 env ✓/✗、推荐脚本  
2. `butler onboard --profile gateway` 与 `effective_operating_profile()` 一致时无矛盾  
3. `tests/test_onboard_cli.py` ≥3 cases  

---

## 3. PROD-P6-02 · `/诊断` 出站失败人话

### 问题

Owner 无回复时只能翻 log；简要 `/诊断` 未提示出站积压/失败。

### 范围

| 做 | 不做 |
|----|------|
| `format_owner_diagnostic_brief` 在 outbox failed / 队列积压时增一行人话 | 替换 `/诊断 详细` |
| 链 `wechat-gateway-ops` | 自动 repair |

### 验收

1. 无出站问题时 **不** 增行（保持三行主体）  
2. mock `outbox_counts(failed>0)` → 含「发送失败」与运维指引  
3. `tests/test_owner_surface.py` 扩展  

---

## 4. PROD-P6-03 · 运维节奏脚本

### 问题

运营动作分散在多个脚本，易漏每周 G1-04 打卡。

### 范围

`scripts/butler-ops-cadence.sh`：

| 模式 | 命令 |
|------|------|
| 每周 | `--weekly` → `butler-g1-04-weekly-checkin.sh --log` |
| 发版前 | `--release` → weekly + `butler-owner-ux-p5-gate.sh` + `butler-pytest-fast-gate.sh` |

### 验收

1. `bash scripts/butler-ops-cadence.sh --weekly` exit 0（窗内 closure exit 2 为预期）  
2. `bash scripts/butler-ops-cadence.sh --release` 跑通守门链  

---

## 5. PROD-P6-04 / P6-05（窗满后）

| ID | 触发 | 动作 |
|----|------|------|
| P6-04 | **07-31** 后 | `butler-g1-04-closure-check.sh` → `ot2_closure_ready` 时更新 gap register G1-04 ✅ |
| P6-05 | P6-04 后 | `butler-owner-pmf-report.sh` 解读首周 `/简报`、验收卡、`/反馈` 重试率 |

---

## 6. P6-C 工程债（穿插）

见 [`model-config-maintainability-2026-06.md`](model-config-maintainability-2026-06.md) · roadmap PROD-P0-03（pytest bisect 记录）。

---

## 7. 守门链

```bash
bash scripts/butler-ops-cadence.sh --weekly
bash scripts/butler-ops-cadence.sh --release
bash scripts/butler-owner-ux-p5-gate.sh
```

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-22 | 立项 P6-01～07 · P6-A 实现 onboard + 出站诊断 + ops cadence |
| 2026-06-26 | **P6-A done** — `butler onboard` · `/诊断` 出站行 · `butler-ops-cadence.sh` |
