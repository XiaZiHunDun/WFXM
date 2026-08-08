# Manual Override: `.claude/settings.json` Hook 路径修复

- Status: Pending Owner manual override
- Date: 2026-08-08
- Scope: `.claude/settings.json` 中的 PreToolUse / PostToolUse hook 命令路径
- Related: Task 3 of `docs/superpowers/plans/2026-08-08-wfxm-v5-replacement-implementation-plan.md`

## 背景与受保护原因

基于 R0 计划 commit 政策（"仅新文件可提交"）以及 plan 第 19 行 Owner-only 约束，Implementer 不得直接修改 `.claude/settings.json`，须由 Owner 手动执行。`.claude/settings.json` 同时承担 AI 守卫配置职责，任何自动修改都可能自我解除 hooks 防线，因此本任务仅以本文档形式交付，不在 implementer 流程内改动。

> 注意：截至 2026-08-08 `.claude/settings.json` 有未提交 v2-shape 修改，应用前 Owner 评估独立提交。

R0 commit 范围的强约束明确“仅新文件可提交”，因此本文档仅以说明形式交付，不直接执行 hook 配置改动。

## 待修复问题

`.claude/settings.json` 中 hook `command` 字段目前使用相对路径，例如：

```json
"command": "python3 scripts/ai_guard/pre_tool_use_hook.py"
```

该相对路径在工作树被移动（例如 worktree、根目录非 cwd）时会失效，导致 hook 解析失败。

## 推荐方案（两种任选其一）

### 方案 A：使用 `$CLAUDE_PROJECT_DIR` 环境变量（推荐）

Claude Code 在每个 hook 调用前会注入项目根目录到 `$CLAUDE_PROJECT_DIR`，使用该变量保证路径稳定：

```json
"command": "python3 $CLAUDE_PROJECT_DIR/scripts/ai_guard/pre_tool_use_hook.py"
```

优点：

- 不依赖 shell 当前工作目录；
- 在 worktree、子目录运行等场景下都解析到正确项目根；
- 与 Claude Code 官方推荐做法一致。

### 方案 B：硬编码项目绝对路径（仅在方案 A 不可行时使用）

如果当前 hook 配置不支持 `$CLAUDE_PROJECT_DIR`（旧版 harness），可使用绝对路径：

```json
"command": "python3 /home/ailearn/projects/WFXM/scripts/ai_guard/pre_tool_use_hook.py"
```

注意：

- 仅在该机器确实是项目根 `/home/ailearn/projects/WFXM` 时有效；
- 路径变更（如 worktree 重命名）会失效；
- 建议作为短期 fallback，长期仍切回方案 A。

## Owner 操作步骤

1. 打开 `/home/ailearn/projects/WFXM/.claude/settings.json`；
2. 定位 `hooks.PreToolUse[].command`（以及 `PostToolUse[].command` 若同样存在相对路径）；
3. 按方案 A 或方案 B 替换原命令；
4. 保存文件；
5. 执行下方验证命令。

## 验证

```bash
# 验证 hook 脚本存在且可解析
python3 $CLAUDE_PROJECT_DIR/scripts/ai_guard/pre_tool_use_hook.py --help
```

期望输出：

- hook 脚本能被解析（`--help` 触发 Python 加载模块）；
- 输出脚本自身的 usage 提示信息或正常退出 0；
- 不报 `No such file or directory` 或 `ModuleNotFoundError`。

附加验证（仅当 hook 在 harness 中被触发时）：

- 启动任意 Claude Code 会话；
- 触发一次 Write/Edit 操作；
- 确认 hook 日志（参见 hook 脚本 stdout/stderr 通道）正常输出。

## 注意事项

- 本文档不执行任何 git 操作；
- 不修改 `.claude/settings.json`、`.cursorrules`、`AGENTS.md`、`butler-v5/` 任何其它文件；
- 不 stage 或 commit 任何既有 M/D/?? 文件；
- 修改完成后由 Owner 自行决定是否纳入后续 R0/R1 commit。
