# OSS 门面 5 件套 + CHANGELOG 回填 — Design Spec

**日期**：2026-09-21
**作者**：owner + Claude (brainstorming flow)
**状态**：✅ Approved (Section 1-5 全 approved)
**Cycle**：D76 (cycle 22)
**Ship 累計目标**：21 → 26 → **110 ship**

## 背景与动机

WFXM 项目已完成 21 cycles × 5 ship = 105 ship 累計（D55→D75），内部基础设施成熟（lint/typecheck 7/7 / test:full 2073 / acceptance 96·96 / methodology 13·13 / knip 0）。但作为对外可见的成熟开源产品，仍缺 5 件门面文件：

- **CHANGELOG.md** — 用户看不到版本演进
- **CODE_OF_CONDUCT.md** — 缺社区规范
- **SECURITY.md** — 缺漏洞披露政策
- **`.github/ISSUE_TEMPLATE/`** — 缺 issue 模板
- **`.github/PULL_REQUEST_TEMPLATE.md`** — 缺 PR 模板

5 件套全为 docs/content 类变更，无代码逻辑变化，可借 D-series 5-batch 纪律复用 21 cycles 沉淀的 audit + gates + acceptance + methodology 基础设施。

## 设计决策汇总

| 维度 | 决定 | 原因 |
|------|------|------|
| 语言 | **中文主**（5 件全中文） | 项目内部惯例延续（AGENTS.md / STRUCTURE.md / docs/architecture/ 都是中文） |
| CHANGELOG | **Keep-a-Changelog 中文版 + D55→D75 回填** | OSS 事实标准 + 用户可见完整演进；回填压缩到 v5.0.0 单一节 |
| Issue 模板 | **Bug + Feature + Question (3 个)** | 覆盖三类常见场景；security 走 SECURITY.md 不开模板 |
| SECURITY | **GitHub Security Advisories + 邮箱备份** | 主流生态 + 兜底；零配置走 GH Advisories |
| CoC | **CC v2.1 官方中文翻译版** | 事实标准；降低法律审视成本 |
| 交付节奏 | **D-series 5-batch (T1-T5)** | 匹配 21 cycles 5 ship 节奏；单 PR 可回滚 |
| v5.0.0 版本基线 | 2026-09-21 = D75 T1 ship 日期 | 与"v5 产品主线"品牌一致 |
| PR 模板自检项 | **§3 / KNOWN_ENTRY_POINTS / actor / owner-jargon / secrets** 全列 | 与 D-series 21 cycles audit 纪律一致；外部贡献者也能自检 |

---

## §1 文件清单与位置

| 文件 | 位置 | 大致行数 | 内容来源 |
|------|------|---------|---------|
| CHANGELOG.md | repo root | ~150-200 | Keep-a-Changelog v1.1.0 中文版骨架 + D55→D75 回填 |
| CODE_OF_CONDUCT.md | repo root | ~150 | Contributor Covenant v2.1 中文翻译版 + 联系方式 |
| SECURITY.md | repo root | ~60-100 | GitHub Security Advisories 流程 + 邮箱 + Supported Versions 表 |
| .github/ISSUE_TEMPLATE/bug_report.md | .github/ | ~40-60 | 标准 bug 模板（环境/重现/期望/实际/截图） |
| .github/ISSUE_TEMPLATE/feature_request.md | .github/ | ~30-50 | 标准 feature 模板（动机/方案/替代/优先级） |
| .github/ISSUE_TEMPLATE/question.md | .github/ | ~20-40 | 简版问题模板（场景/已查资料/期望） |
| .github/ISSUE_TEMPLATE/config.yml | .github/ | ~15-25 | GitHub issue 选择器配置（指向 SECURITY.md） |
| .github/PULL_REQUEST_TEMPLATE.md | .github/ | ~30-50 | 复选清单（关联 issue / 测试 / 自检 / 截图） |

**总产出：8 个文件 / 约 425-645 行净增。**

**关键设计取舍：**

1. CHANGELOG.md 放 repo root 而非 butler-v5/——项目根 README.md 引用要一致
2. CoC 用 CC v2.1 官方 zh-cn 翻译版（contributor-covenant.org/zh-cn/version/2/1）而非自定义——降低法律审视成本且事实标准
3. SECURITY.md 用 GitHub Security Advisories 为主披露路径 + 联系邮箱兜底——避免重复
4. Issue 模板 3 个而非 4 个——security 类走 SECURITY.md 而非 Issue（避免敏感信息误公开）
5. config.yml 显式指向 SECURITY.md——把"安全洞"导入正确披露路径
6. 不动 butler-v5/ 下已有同类型文件——本次只补 root + .github/ 缺失项，避免重复维护
7. CHANGELOG.md 顶部加 link "v5 子项目发布节奏见 butler-v5/CHANGELOG.md"——避免双轨分歧

---

## §2 CHANGELOG.md 内容策略

### 版本方案

- 首版以 **v5.0.0** 为基线（匹配 "Butler v5" 品牌），日期 2026-09-21 = D75 T1 ship 日期
- 无 tag → 比较 URL 用 commit SHA 作 anchor：`[v5.0.0]: https://github.com/XiaZiHunDun/WFXM/commits/b11cdfdb`
- 后续 release 沿用 SemVer：`[5.1.0] - YYYY-MM-DD`（用户可见 release）+ D-series audit cycle（内部 commit 节奏）

### Section 结构（Keep-a-Changelog v1.1.0 中文版）

```
# 更新日志

本项目所有重要变更都会记录在此文件。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

## [5.0.0] - 2026-09-21
### 新增 (Added)
### 变更 (Changed)
### 修复 (Fixed)
### 弃用 (Deprecated)
### 移除 (Removed)
### 安全 (Security)

[5.0.0]: https://github.com/XiaZiHunDun/WFXM/commits/b11cdfdb
```

### 回填策略：D55→D75 = 21 cycles / 105 ships 压缩到单一 v5.0.0

按**用户视角类别**聚合（而非按 cycle 列），4 类核心 + 1 可选：

#### 新增 (Added)
- 多渠道消息网关（微信 iLink 原生文本/图片/文件/语音）
- AgentKernel 驱动的 LLM + 结构化工具循环
- 子代理委派、PostgreSQL Outbox 与 WebSocket 异步推送
- PostgreSQL Event Store + PGlite 测试隔离
- 多 Provider LLM 与失败降级
- §18 undo 机制（5 工具/链式撤销）+ §12 自动升级候选
- 跨项目主键 recall（§18 row 3）
- 工作区具名命令执行 + 文件回传

#### 安全 (Security) — 21 cycles 安全 trio 闭环
- SEC-001/006: Telegram webhook replay dedup + 敏感凭证 Secret<T> 包装
- SEC-002 DNS rebinding 防御
- SEC-003 IPv6 false positive 修正
- SEC-004 渠道入站共享密钥一致性
- SEC-005 Telegram media cache path-traversal 防御
- WS caller forgery 修复 (SEC-001 D73)
- HTTP headers 强化 (SEC-006 D71)
- umask 加固 (SEC-007 D71)

#### 修复 (Fixed)
- 21 cycles audit findings 中修复的 bug
- 47+ owner-jargon 中英文泄漏点替换为安全文案
- 4th cycle carry: fatigue_signal populate
- 13-cycle CQ carry patterns 收敛

#### 变更 (Changed) — 重构与质量
- 内部：从 Hermes AIAgent 解耦（ADR-0001）
- 21 cycles 跨 D-series 重构：CQ-002/003/004/005 god-fn 拆解
- 13 DEFAULT_*_TIMEOUT_MS 统一（packages/adapters/defaults.ts）
- workspace-tools 独立撤销模块 + KNOWN_ENTRY_POINTS 更新
- 105 ship 累計中 ~1500 行内联错误码收敛为 8+ helper

#### 性能 (Performance) — 可选小节
- 96·96 acceptance 持续稳定
- subagent-worker 807→773 行瘦身
- routes.ts channel-handler 583→81 拆分

### 回填数据源

1. `git log --oneline b11cdfdb` (倒序 21 cycles × 5 ship = 105 commits)
2. `.audit/D55/` ~ `.audit/D74/` raw findings JSON (filter must-fix)
3. `memory/project-fix-D55-..-D74-...md` 已写的人类可读总结
4. `butler-v5/DESIGN.md` 当前能力列表
5. `docs/architecture/` 高层架构演进文档

### 回填工作量

- 数据收集（git + audit + memory grep）：~30 min
- 用户视角类别翻译（audit ID → user-facing）：~60 min（核心工作量）
- CHANGELOG 排版 + 链接：~30 min
- 验证（不漏 must-fix / 链接有效 / 日期准确）：~15 min
- **合计 ~2-2.5h**

---

## §3 CoC + SECURITY 内容策略

### CODE_OF_CONDUCT.md

**内容来源：**
- 主体：[Contributor Covenant v2.1 官方中文翻译版](https://www.contributor-covenant.org/zh-cn/version/2/1/code_of_conduct/) (~140 行翻译原文)
- 顶部项目名替换 + 联系方式插桩 (~10 行 owner-specific)
- 不删减原文条款（降低法律审视成本 + 事实标准）

**结构骨架：**
```markdown
# 贡献者公约 (Contributor Covenant)
## 我们的承诺
## 我们的标准
## 我们的责任
## 范围
## 执行
## 归属

## 项目联系方式
- **执行联系**：[新建 Issue](https://github.com/XiaZiHunDun/WFXM/issues/new) 并打 `conduct` 标签
- **执行升级**：如对执行结果不满，可联系 GitHub 平台支持

[v2.1]: https://www.contributor-covenant.org/zh-cn/version/2/1/code_of_conduct/
```

**执行联系决定：GitHub Issues with `conduct` 标签**
- 零设置成本
- 公开透明
- 适合单 owner 项目

### SECURITY.md

**结构骨架：**
```markdown
# 安全策略 (Security Policy)

## 支持的版本 (Supported Versions)
| 版本 | 支持状态 |
|------|---------|
| v5.x | ✅ 活跃支持 |
| v4.x | ❌ 已 EOL（见 ADR-0001） |
| < v4 | ❌ 不支持 |

## 披露漏洞 (Reporting a Vulnerability)

### 推荐路径：GitHub Security Advisories
1. 打开项目仓库 → Security tab → "Report a vulnerability"
2. 填写私密披露表单（GitHub 端到端加密）
3. 我们将：
   - **48 小时内**首次响应
   - 评估严重性并沟通修复时间线
   - 修复后通过 GitHub Security Advisory 公开致谢 + CVE ID（如适用）
   - 修复 release 标注 `🔒 security` 标签

### 备选路径：邮件
- 邮箱：`security@wfxm.dev`
- 适用：不方便用 GitHub 的报告者
- PGP 密钥：项目暂未提供（GitHub Advisories 默认加密足够）

## 安全更新订阅
- Watch → Custom → "Releases only"
- CHANGELOG.md "Security" 小节记录所有修复

## 安全最佳实践（部署者侧）
- 始终运行最新 v5.x release
- 不在公网暴露 owner-route；走 SSH tunnel 或 wireguard
- secrets 通过 `wfxm secret set` 加密存储（见 SECURITY 文档）
- 启用 audit emit（如未默认）
```

**关键内容决策：**

| 决策点 | 默认值 | 取舍 |
|--------|--------|------|
| 邮箱后缀 | `wfxm.dev` 占位 | 需 owner 后续在 GitHub email forwarding 配置；标"待 owner 注册" |
| 首次响应 SLA | 48 小时 | 单 owner 现实承诺 |
| Supported Versions 范围 | v5.x 全支持 | 与 ADR-0001 v4 EOL 一致 |
| Security Advisories 流程 | 启用 | GH 原生；免费；支持 CVE |
| Out-of-scope 列表 | **不加** | 单 owner 项目争议成本 < 明确成本 |

---

## §4 Issue 模板 + PR 模板内容策略

### .github/ISSUE_TEMPLATE/bug_report.md

```markdown
---
name: 🐛 Bug 报告
about: 报告一个具体 bug 或异常行为
title: '[Bug] '
labels: ['bug', 'triage']
assignees: []
---

## 描述
<清晰描述发生了什么>

## 复现步骤
1. 
2. 
3. 

## 期望行为
<按文档预期应该发生什么>

## 实际行为
<实际发生了什么>

## 环境
- **WFXM 版本**：v5.x.y（`git describe --tags` 或 `wfxm --version`）
- **部署模式**：自托管 / Docker / pnpm dev
- **OS**：Linux/macOS/Windows 版本
- **Node.js 版本**：`node --version`
- **数据库**：PostgreSQL 版本 / PGlite（开发）
- **LLM Provider**：Anthropic/OpenAI/其他 + 模型名

## 严重程度
- [ ] 🔴 阻塞（核心功能不可用）
- [ ] 🟡 降级（有 workaround）
- [ ] 🟢 轻微（边界 / 文案）

## 截图 / 日志
<!-- 粘贴 `wfxm debug bundle` 输出或 owner-side error 截图 -->

## 自检
- [ ] 已搜索 [已有 issues](https://github.com/XiaZiHunDun/WFXM/issues?q=is%3Aissue+bug) 无重复
- [ ] 已查阅 [docs/](https://github.com/XiaZiHunDun/WFXM/tree/main/docs) 和 [butler-v5/README.md](https://github.com/XiaZiHunDun/WFXM/tree/main/butler-v5)
- [ ] 已查阅 [CHANGELOG.md](https://github.com/XiaZiHunDun/WFXM/blob/main/CHANGELOG.md) 确认非已知回归
- [ ] ⚠️ **安全问题**：漏洞请走 [SECURITY.md](https://github.com/XiaZiHunDun/WFXM/blob/main/SECURITY.md)，不要在此公开
```

### .github/ISSUE_TEMPLATE/feature_request.md

```markdown
---
name: ✨ 功能请求
about: 提议新功能或能力扩展
title: '[Feature] '
labels: ['enhancement', 'triage']
assignees: []
---

## 动机
<解决什么问题 / 哪个场景需要>

## 提议方案
<高层方案；不需完整设计>

## 替代方案
<考虑过哪些替代，为什么不选>

## 优先级（自评）
- [ ] P0（核心能力缺口）
- [ ] P1（重要但有 workaround）
- [ ] P2（nice-to-have）

## 关联
- 关联 issue / discussion / 文档章节：

## 验收标准
- [ ] 验收标准 1
- [ ] 验收标准 2
```

### .github/ISSUE_TEMPLATE/question.md

```markdown
---
name: ❓ 问题 / 文档
about: 询问用法、寻求文档澄清
title: '[Question] '
labels: ['question']
assignees: []
---

## 场景
<在做什么 / 卡在哪里>

## 已查资料
- [ ] [README.md](https://github.com/XiaZiHunDun/WFXM/blob/main/README.md)
- [ ] [butler-v5/README.md](https://github.com/XiaZiHunDun/WFXM/tree/main/butler-v5/README.md)
- [ ] [AGENTS.md](https://github.com/XiaZiHunDun/WFXM/blob/main/AGENTS.md)
- [ ] [docs/architecture/](https://github.com/XiaZiHunDun/WFXM/tree/main/docs/architecture)
- [ ] [已有 issues](https://github.com/XiaZiHunDun/WFXM/issues?q=is%3Aissue+question)

## 期望答案
<具体希望得到什么——配置示例 / 文档指针 / 设计解释>
```

### .github/ISSUE_TEMPLATE/config.yml

```yaml
# GitHub Issue 选择器配置
blank_issues_enabled: false  # 强制走模板
contact_links:
  - name: 🔒 安全漏洞披露
    url: https://github.com/XiaZiHunDun/WFXM/blob/main/SECURITY.md
    about: 请勿在公开 Issue 提交漏洞；走 GitHub Security Advisories 或邮件
  - name: 📖 架构与设计文档
    url: https://github.com/XiaZiHunDun/WFXM/tree/main/docs/architecture
    about: 系统设计、ADR、layer-theory 等
```

> **决定**：去掉"一般讨论"链接（GitHub Discussions 未启用，链接会 404）。

### .github/PULL_REQUEST_TEMPLATE.md

```markdown
## 关联
- closes #XX / fixes #XX / refs #XX

## 变更摘要
<!-- 1-3 句话讲做了什么 -->

## 变更类型
- [ ] feat（新功能）
- [ ] fix（bug 修复）
- [ ] refactor（重构，无行为变化）
- [ ] docs（文档）
- [ ] test（测试）
- [ ] chore（杂项）
- [ ] 🔒 security（安全修复）

## 影响面
- [ ] 触及 §3 边界（domain / adapters / apps）
- [ ] 触及 KNOWN_ENTRY_POINTS（routes/inbound.ts 等）
- [ ] 触及 audit emit（actor 字段）
- [ ] 触及 owner-jargon 文案（用 safeOwnerErrorString 等 helper）
- [ ] 触及 secrets（Secret<T> 包装）

## 测试
- [ ] `pnpm lint` 通过
- [ ] `pnpm typecheck` 通过
- [ ] `pnpm test:full` 通过（含本变更覆盖）
- [ ] `pnpm acceptance` 通过（如触及 §X 行为）
- [ ] 新增/修改测试覆盖本变更

## 自检清单
- [ ] commit message 符合 conventional commits（feat/fix/refactor/...）
- [ ] 代码遵循 `docs/architecture/` 已记录的模式
- [ ] 无 hardcoded secrets / credentials
- [ ] 无 console.log / 调试残留
- [ ] CHANGELOG.md（如适用）已更新
- [ ] AGENTS.md / STRUCTURE.md（如有目录变更）已同步

## 截图 / 录屏
<!-- UI / owner-jargon 文案 / 错误处理可视化等 -->

## 上游同步检查
- [ ] 如触及 butler-v5 子项目，确认 root 与 subproject 同步
```

**模板关键设计取舍：**

| 决策 | 默认 | 理由 |
|------|------|------|
| Issue 模板强制启用（blank_issues_enabled: false） | 启用 | 降低噪音 + 强制自检 |
| bug 模板含 SECURITY 自检 + Issue body 警示 | 启用 | 引导漏洞走 SECURITY.md 私密披露 |
| PR 模板含 §3 / KNOWN_ENTRY_POINTS / actor / owner-jargon / secrets 自检 | 启用 | 与 D-series 21 cycles audit 纪律一致 |
| PR 模板含"上游同步检查"（root ↔ butler-v5） | 启用 | 项目双轨结构风险 |
| assignees 留空 | 留空 | 单 owner 自动承接 |

---

## §5 5-batch 交付 schedule

### Cycle 22 (D76) 整体规划

**目标：补齐 🔴 OSS 门面 5 件套 + CHANGELOG 回填，5 个 commit 落地。**

### T1: CHANGELOG.md 回填（D55→D75）

**Commit message：**
```
chore(docs) D76 T1 close OSS-CHANGELOG: Keep-a-Changelog 中文版 + D55→D75 105-ship 回填
```

**Files touched：**
- ✏️ `CHANGELOG.md` (new, ~150-200 行)

**工作量：~2-2.5h**

**风险：**
- 回填遗漏（漏掉 must-fix） → 验证：grep audit ID 必现
- 链接 404（commit SHA 失效）→ 验证：每个 anchor 检查
- 日期错乱 → 验证：逐条 commit date 对照

**Verification：**
```bash
# 1. 文件存在且非空
[ -s CHANGELOG.md ]

# 2. 必须含 Keep-a-Changelog 类别小标题
grep -E "^### (新增|修复|安全|变更)" CHANGELOG.md

# 3. must-fix 覆盖度（粗略抽样）
SEC_KEYWORDS="SEC-001|SEC-002|SEC-003|SEC-004|SEC-005|SEC-006|SEC-007|SEC-008"
grep -cE "$SEC_KEYWORDS" CHANGELOG.md  # ≥10

# 4. 链接 anchor 格式
grep -E "^\[[0-9.]+\]: https://github.com/XiaZiHunDun/WFXM" CHANGELOG.md
```

### T2: CoC + SECURITY 治理文件

**Commit message：**
```
chore(docs) D76 T2 close OSS-COC + OSS-SECURITY: Contributor Covenant v2.1 中文版 + GitHub Security Advisories
```

**Files touched：**
- ✏️ `CODE_OF_CONDUCT.md` (new, ~150 行)
- ✏️ `SECURITY.md` (new, ~80 行)

**工作量：~1-1.5h**

**风险：**
- CC v2.1 翻译版遗漏署名 → 验证：底部 CC 链接
- SECURITY 邮箱占位未明确 → 验证：注释"待 owner 注册"
- Supported Versions 与 ADR-0001 不一致 → 验证：grep `v4.x`

**Verification：**
```bash
# 1. CoC 关键章节齐
grep -E "^## (我们的承诺|我们的标准|我们的责任|范围|执行)" CODE_OF_CONDUCT.md

# 2. CoC 归属链接
grep -E "contributor-covenant.org.*version/2/1" CODE_OF_CONDUCT.md

# 3. SECURITY 关键章节
grep -E "## (支持版本|披露漏洞|首次响应|安全更新)" SECURITY.md

# 4. SECURITY ADR-0001 一致性
grep -E "v4\.x.*EOL|ADR-0001" SECURITY.md
```

### T3: 3 Issue 模板 + config.yml

**Commit message：**
```
chore(docs) D76 T3 close OSS-ISSUE-TPL: Bug + Feature + Question 模板 + config.yml 选择器
```

**Files touched：**
- ✏️ `.github/ISSUE_TEMPLATE/bug_report.md` (new, ~50 行)
- ✏️ `.github/ISSUE_TEMPLATE/feature_request.md` (new, ~40 行)
- ✏️ `.github/ISSUE_TEMPLATE/question.md` (new, ~30 行)
- ✏️ `.github/ISSUE_TEMPLATE/config.yml` (new, ~20 行)

**工作量：~30-45min**

**风险：**
- YAML frontmatter 缩进错误 → GitHub 解析失败 → 验证：lint
- config.yml contact_links URL 404 → 验证：手工检查每条 URL
- Issue 选择器渲染异常 → 验证：本仓库预览

**Verification：**
```bash
# 1. 4 个文件齐全
ls .github/ISSUE_TEMPLATE/{bug_report,feature_request,question}.md .github/ISSUE_TEMPLATE/config.yml

# 2. YAML 语法
python -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/config.yml'))"

# 3. 每个模板 frontmatter 含 name + about
for f in bug_report feature_request question; do
  grep -E "^name:|^about:" .github/ISSUE_TEMPLATE/$f.md
done

# 4. 模板含 SECURITY 引导
grep -E "SECURITY\.md" .github/ISSUE_TEMPLATE/bug_report.md
```

### T4: PR 模板

**Commit message：**
```
chore(docs) D76 T4 close OSS-PR-TPL: PR 复选清单模板（含 §3/KNOWN_ENTRY_POINTS/actor/secrets 自检）
```

**Files touched：**
- ✏️ `.github/PULL_REQUEST_TEMPLATE.md` (new, ~45 行)

**工作量：~15-20min**

**风险：**
- markdown checkbox 嵌套错误 → 渲染异常 → 验证：lint
- §20 invariant 引用过时 → 与 T1 一致性 → 验证：grep

**Verification：**
```bash
# 1. 文件存在
[ -s .github/PULL_REQUEST_TEMPLATE.md ]

# 2. 必含 §3 / KNOWN_ENTRY_POINTS / actor / owner-jargon / secrets 自检项
for kw in "§3" "KNOWN_ENTRY_POINTS" "actor" "owner-jargon" "Secret<T>" "secrets"; do
  grep -q "$kw" .github/PULL_REQUEST_TEMPLATE.md
done

# 3. Conventional commits 类型提示
grep -E "feat|fix|refactor|docs|test|chore" .github/PULL_REQUEST_TEMPLATE.md
```

### T5: 交叉验证 + methodology check

**Commit message：**
```
chore(docs) D76 T5 close OSS-VALIDATE: cross-validation + acceptance scenarios + methodology 13·13
```

**Files touched：**
- ✏️ `tests/acceptance/scenarios_oss_handbook.md` (new, ~80-120 行)

**工作量：~30min**

**内容：**
- 4 个 acceptance scenarios (CHANGELOG 链接有效 / CoC 链接有效 / Issue 模板渲染 / PR 模板渲染)
- 1 个 methodology check (OSS 5 件套文件齐 + 内容非空 + 与 ADR-0001/§20 一致)

**Verification：**
```bash
# 1. OSS 5 件套文件齐
for f in CHANGELOG.md CODE_OF_CONDUCT.md SECURITY.md \
         .github/ISSUE_TEMPLATE/bug_report.md \
         .github/ISSUE_TEMPLATE/feature_request.md \
         .github/ISSUE_TEMPLATE/question.md \
         .github/ISSUE_TEMPLATE/config.yml \
         .github/PULL_REQUEST_TEMPLATE.md; do
  [ -s "$f" ] && echo "✓ $f" || echo "✗ MISSING $f"
done

# 2. methodology 13·13 → 14·14
pnpm methodology

# 3. acceptance 96·96 → 100·100 (+4 新场景)
pnpm acceptance

# 4. 全 gates 不退化
pnpm lint && pnpm typecheck && pnpm test:full
```

---

## 🎯 Cycle 22 总结

| T | Files | Workload | Risk |
|---|-------|----------|------|
| T1 | CHANGELOG.md | 2-2.5h | 回填遗漏 / 链接失效 |
| T2 | CoC + SECURITY | 1-1.5h | 翻译版遗漏 / ADR 一致性 |
| T3 | 3 Issue + config | 30-45min | YAML 缩进 / 链接 404 |
| T4 | PR 模板 | 15-20min | checkbox 嵌套 |
| T5 | acceptance + methodology | 30min | scenario 设计 |
| **合计** | **8 文件** | **~5-6h** | — |

**Ship 累計：21 → 26（cycle 22 加 5 ship）= 110 ship 累計**

**风险评估（整体）：**
- 全部为 content/docs 工作，无代码逻辑变更
- D-series 21 cycles 的基础设施（gates / acceptance / methodology / audit）天然覆盖本次变更
- 唯一非平凡风险：T1 回填遗漏——靠 audit ID grep 兜底
- T5 是必做 gate，确保 cycle 闭环

---

## 取舍问题与决定

| # | 决定点 | 选择 | 原因 |
|---|--------|------|------|
| Q1 | butler-v5/CHANGELOG.md 已存在，root 版是否要 link | **link** "v5 子项目版本见 butler-v5/CHANGELOG.md" | 避免重复维护 + 双轨分歧 |
| Q2 | v5.0.0 节要不要单独列 Known Limitations | **放在 Changed 末段 "已知限制"小节**，link 到 v5-production-architecture | 集中管理 + 链接引用 |
| Q3 | root 版要不要 include butler-v5/CHANGELOG.md 旧内容 | **不 include**，顶部 link | 单一可信源原则 |
| Q4 | CoC 执行联系走 Issue 路径还是邮箱 | **A：Issue + `conduct` 标签** | 零配置 + 公开透明 |
| Q5 | SECURITY 邮箱后缀 | **`wfxm.dev` 占位 + "待 owner 注册"标注** | 保留升级路径 |
| Q6 | SECURITY 要不要加 Out-of-scope 小节 | **不加** | 单 owner 争议成本 > 明确成本 |
| Q7 | PR 模板 §3 / KNOWN_ENTRY_POINTS / actor / owner-jargon / secrets 全列 | **全列 + 注释 "如不确定，可问 owner"** | 内外兼顾 |
| Q8 | contact_links 第三个"一般讨论"链接 | **去掉** | GitHub Discussions 未启用 |
| Q9 | T1 工作量最大要不要拆 T1a+T1b | **不拆，单 commit + 中间 checkpoint** | 简化但保留审校 |
| Q10 | T5 acceptance scenarios 4 个够吗 | **4 个，匹配 D52 acceptance harness 扩 pattern** | 不过度设计 |

---

## Verification 整体计划

每个 T 完成后必跑：
1. 文件存在 + 非空（`[ -s $f ]`）
2. 关键内容 grep 命中（验证模板骨架齐）
3. 链接格式正确（CHANGELOG anchor / SECURITY 邮箱 / contact_links URL）
4. ADR-0001 / §20 invariant 一致性（cross-cycle 引用不破）

T5 完成后必跑全 gates：
- `pnpm lint` / `pnpm typecheck` / `pnpm test:full`
- `pnpm acceptance` (96·96 → 100·100)
- `pnpm methodology` (13·13 → 14·14)
- `pnpm knip` (0 → 0)

---

## Out of Scope（不在本次 cycle 处理）

以下 OSS 缺口留待后续 cycle：
- `Dockerfile` (root, production-grade)
- `.github/dependabot.yml`
- `ROADMAP.md` 或 GitHub Projects 公开链接
- 架构可视化 (Mermaid / PNG)
- FAQ.md + TROUBLESHOOTING.md
- `README.zh.md` 双语 README 拆分
- `.github/FUNDING.yml`
- `.github/workflows/release.yml`
- `CODEOWNERS`
- `GOVERNANCE.md`
- Demo deployment / 在线演示

预计作为 cycle 23+ 的 OSS 治理下一批。

---

## Related

- **Memory**：[[project-pause-state-post-D75-T1-2026-09-21]]（D75 T1 pause）
- **ADR**：[[docs/adr/2026-08-08-v4-to-v5-supersession]]（v4 EOL 引用）
- **Specs**：
  - [[docs/architecture/v5-production-architecture-2026-08.md]]（v5 当前能力）
  - [[butler-v5/DESIGN.md]]（v5 子项目设计）
  - [[butler-v5/CHANGELOG.md]]（v5 子项目版本）
- **D-series ship 累計**：21 cycles × 5 ship = 105 (D55→D75) → cycle 22 加 5 → **110 ship**
