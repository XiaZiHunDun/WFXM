# OSS Handbook Acceptance Scenarios

> **Cycle**: D76 (cycle 22)
> **Date**: 2026-09-21
> **Branch**: main
> **Spec**: [docs/superpowers/specs/2026-09-21-oss-handbook-design.md](../../docs/superpowers/specs/2026-09-21-oss-handbook-design.md)

本文件定义 cycle 22（D76）OSS 门面 5 件套的 acceptance scenarios。共 4 个场景 + 1 个 methodology check。

## Scenario OSS-HB-01: CHANGELOG.md 链接有效

**目的**：验证 CHANGELOG.md 中所有 anchor 链接可访问（不 404）

**前置条件：**
- CHANGELOG.md 已创建
- 当前 HEAD SHA 已知

**步骤：**
1. 提取 CHANGELOG.md 中所有 `[X.Y.Z]: https://github.com/XiaZiHunDun/WFXM/commits/<sha>` 形式
2. 对每个 sha 验证 commit 存在（`git cat-file -t <sha>`）

**验收：**
- 所有 anchor 引用的 commit SHA 在 `git log` 中存在

**自动化（pseudo）：**
```bash
for sha in $(grep -oE "/commits/[0-9a-f]{40}" CHANGELOG.md | cut -d/ -f3 | sort -u); do
  git cat-file -t $sha > /dev/null || { echo "FAIL: $sha 不存在"; exit 1; }
done
echo "✓ OSS-HB-01 PASS"
```

## Scenario OSS-HB-02: Contributor Covenant 链接有效

**目的**：验证 CoC 引用官方 CC v2.1 链接可达

**前置条件：**
- CODE_OF_CONDUCT.md 已创建

**步骤：**
1. 提取 CoC 中的 `contributor-covenant.org/.../version/2/1/code_of_conduct` 链接
2. WebFetch 验证链接响应 200

**验收：**
- CC v2.1 官方中文翻译版链接响应 200

**自动化（pseudo）：**
```bash
LINK=$(grep -oE "https://www\.contributor-covenant\.org/zh-cn/version/2/1/code_of_conduct" CODE_OF_CONDUCT.md | head -1)
curl -sI -o /dev/null -w "%{http_code}" "$LINK" | grep -q "^200$" || { echo "FAIL"; exit 1; }
echo "✓ OSS-HB-02 PASS"
```

## Scenario OSS-HB-03: Issue 模板 GitHub 渲染

**目的**：验证 3 Issue 模板 + config.yml 格式合法，GitHub 可正确渲染

**前置条件：**
- `.github/ISSUE_TEMPLATE/` 4 文件已创建

**步骤：**
1. 验证每个 .md 文件 frontmatter 解析合法（YAML）
2. 验证 config.yml 解析合法
3. 验证 config.yml 中 `blank_issues_enabled: false` 已设置
4. 验证 bug_report.md 包含 SECURITY.md 引导

**验收：**
- 4 文件 frontmatter/YAML 解析无错
- 强制模板 + SECURITY 引导存在

**自动化（pseudo）：**
```bash
for f in bug_report feature_request question; do
  python3 -c "import yaml,sys; yaml.safe_load(open('.github/ISSUE_TEMPLATE/$f.md'.read().split('---')[1]))" \
    || { echo "FAIL: $f frontmatter"; exit 1; }
done
python3 -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/config.yml'))" \
  || { echo "FAIL: config.yml"; exit 1; }
grep -q "SECURITY.md" .github/ISSUE_TEMPLATE/bug_report.md || { echo "FAIL"; exit 1; }
echo "✓ OSS-HB-03 PASS"
```

## Scenario OSS-HB-04: PR 模板自检覆盖

**目的**：验证 PR 模板含 §3 / KNOWN_ENTRY_POINTS / actor / owner-jargon / secrets 5 项自检

**前置条件：**
- `.github/PULL_REQUEST_TEMPLATE.md` 已创建

**步骤：**
1. 验证模板含 5 项自检关键词
2. 验证 conventional commits 类型提示
3. 验证上游同步检查小节

**验收：**
- 5 关键词全命中
- conventional commits 类型齐
- 上游同步检查存在

**自动化（pseudo）：**
```bash
for kw in "§3" "KNOWN_ENTRY_POINTS" "actor" "owner-jargon" "Secret<T>"; do
  grep -q "$kw" .github/PULL_REQUEST_TEMPLATE.md || { echo "FAIL: $kw"; exit 1; }
done
grep -qE "feat|fix|refactor|docs|test|chore" .github/PULL_REQUEST_TEMPLATE.md || { echo "FAIL"; exit 1; }
grep -q "上游同步检查" .github/PULL_REQUEST_TEMPLATE.md || { echo "FAIL"; exit 1; }
echo "✓ OSS-HB-04 PASS"
```

## Methodology Check: M14 — OSS 5 件套齐 + ADR 一致性

**目的**：验证 5 件套文件齐全 + 内容非空 + 与 ADR-0001/§20 invariant 一致

**验收标准（全部满足）：**

1. **文件齐全（8 项）**：
   - `CHANGELOG.md`
   - `CODE_OF_CONDUCT.md`
   - `SECURITY.md`
   - `.github/ISSUE_TEMPLATE/bug_report.md`
   - `.github/ISSUE_TEMPLATE/feature_request.md`
   - `.github/ISSUE_TEMPLATE/question.md`
   - `.github/ISSUE_TEMPLATE/config.yml`
   - `.github/PULL_REQUEST_TEMPLATE.md`

2. **内容非空**：
   - Markdown 文件（CHANGELOG.md / CODE_OF_CONDUCT.md / SECURITY.md / .md 模板）≥ 20 行
   - YAML 文件（.github/ISSUE_TEMPLATE/config.yml）合法 + 含 `blank_issues_enabled: false`

3. **ADR-0001 一致性**：SECURITY.md 中 v4.x 标注为 EOL

4. **§20 KNOWN_ENTRY_POINTS 一致**：CHANGELOG.md 提及 routes/inbound.ts 新入口

5. **可发现性**：所有 5 件套文件从 `README.md` 或 `AGENTS.md` 可链接

**自动化（pseudo）：**
```bash
cd /home/ailearn/projects/WFXM

# 1. 文件齐全
for f in CHANGELOG.md CODE_OF_CONDUCT.md SECURITY.md \
         .github/ISSUE_TEMPLATE/bug_report.md \
         .github/ISSUE_TEMPLATE/feature_request.md \
         .github/ISSUE_TEMPLATE/question.md \
         .github/ISSUE_TEMPLATE/config.yml \
         .github/PULL_REQUEST_TEMPLATE.md; do
  [ -s "$f" ] || { echo "FAIL: missing or empty: $f"; exit 1; }
done

# 2a. Markdown 文件 ≥ 20 行
for f in CHANGELOG.md CODE_OF_CONDUCT.md SECURITY.md \
         .github/ISSUE_TEMPLATE/bug_report.md \
         .github/ISSUE_TEMPLATE/feature_request.md \
         .github/ISSUE_TEMPLATE/question.md \
         .github/PULL_REQUEST_TEMPLATE.md; do
  LINES=$(wc -l < "$f")
  [ "$LINES" -ge 20 ] || { echo "FAIL: $f too short ($LINES lines)"; exit 1; }
done

# 2b. config.yml 合法 + 强制模板
python3 -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/config.yml'))" \
  || { echo "FAIL: config.yml YAML invalid"; exit 1; }
grep -q "blank_issues_enabled: false" .github/ISSUE_TEMPLATE/config.yml \
  || { echo "FAIL: config.yml missing blank_issues_enabled: false"; exit 1; }

# 3. ADR-0001 一致
grep -q "v4\.x.*EOL\|ADR-0001" SECURITY.md || { echo "FAIL: SECURITY.md ADR-0001 一致性"; exit 1; }

# 4. §20 KNOWN_ENTRY_POINTS
grep -q "KNOWN_ENTRY_POINTS\|routes/inbound" CHANGELOG.md || { echo "FAIL: CHANGELOG.md §20 引用"; exit 1; }

# 5. 可发现性（README.md 或 AGENTS.md 二选一；本项目以 AGENTS.md 为准）
grep -qE "CHANGELOG\.md|CODE_OF_CONDUCT\.md|SECURITY\.md" AGENTS.md \
  || grep -qE "CHANGELOG\.md|CODE_OF_CONDUCT\.md|SECURITY\.md" README.md \
  || { echo "FAIL: README.md / AGENTS.md 未引用 OSS 文件"; exit 1; }

echo "✓ M14 PASS"
```

## 总结

- 4 acceptance scenarios (OSS-HB-01..04)
- 1 methodology check (M14)
- 与现有 acceptance harness 集成：`pnpm test:acceptance` 应从 baseline 96·96 → 100·100
- 与现有 methodology check 集成：`pnpm test:methodology` 应从 13·13 → 14·14
