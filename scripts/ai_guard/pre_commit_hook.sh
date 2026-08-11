#!/usr/bin/env bash
# git pre-commit hook: IDE 无关的后备保护。
# 在每次 git commit 前运行关键门禁检查。
# 安装: cp scripts/ai_guard/pre_commit_hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "== AI Guard: pre-commit 检查 =="

# 1. 检查是否修改了受保护文件
PROTECTED_FILES=(
    "butler/core/agent_loop/loop.py"
    "butler/contracts/__init__.py"
    "pyproject.toml"
    ".claude/settings.json"
    "scripts/ai_guard/pre_tool_use_hook.py"
    "scripts/ai_guard/post_tool_use_hook.py"
)

VIOLATIONS=0
for pf in "${PROTECTED_FILES[@]}"; do
    if git diff --cached --name-only | grep -q "^${pf}$"; then
        echo "❌ BLOCKED: 受保护文件被修改: $pf"
        echo "   如需修改，请在 commit message 中包含 [MANUAL-OVERRIDE] 标记。"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done

# 允许人工覆盖（commit message 包含 [MANUAL-OVERRIDE]）
if [ "$VIOLATIONS" -gt 0 ]; then
    # 检查 commit message（如果是 commit 操作）
    COMMIT_MSG_FILE="$(git rev-parse --git-dir)/COMMIT_EDITMSG"
    if [ -f "$COMMIT_MSG_FILE" ] && grep -q "\[MANUAL-OVERRIDE\]" "$COMMIT_MSG_FILE"; then
        echo "⚠️  [MANUAL-OVERRIDE] 检测到，允许修改受保护文件。"
    else
        echo ""
        echo "提交被阻止。$VIOLATIONS 个受保护文件被修改。"
        echo "如需人工覆盖，请在 commit message 中添加 [MANUAL-OVERRIDE] 标记。"
        exit 1
    fi
fi

# 2. 检查层依赖（快速版）
if git diff --cached --name-only | grep -qE "^butler/.*\.py$"; then
    echo "→ 运行层依赖检查..."
    if ! python -m pytest tests/test_eng15_layer_dependency_matrix.py -q --tb=line --no-header 2>/dev/null; then
        echo "❌ 层依赖检查失败！"
        echo "   运行完整检查: bash scripts/butler-layer-import-gate.sh"
        exit 1
    fi
    echo "✅ 层依赖检查通过"

    # G1: lazy import 预算检查（仅改 butler/*.py 时）
    echo "→ 运行 lazy import 预算检查..."
    if ! bash scripts/p3i-lazy-import-report.sh 2>/dev/null; then
        echo "❌ Lazy import 预算超限（>1910）！"
        echo "   AI 可能添加了模块级 import 导致循环依赖。"
        echo "   请将新增的 from butler.* 改为函数内 lazy import。"
        echo "   完整报告: bash scripts/p3i-lazy-import-report.sh"
        exit 1
    fi
    echo "✅ Lazy import 预算检查通过"

    # G6: 文件大小守卫
    echo "→ 运行文件大小守卫..."
    if ! python3 scripts/ai_guard/file_size_check.py --staged; then
        echo "❌ 文件大小守卫失败！"
        echo "   项目约定 .py 文件 >800 行应拆分。"
        echo "   如确需大文件，请在 commit message 中包含 [MANUAL-OVERRIDE] 标记。"
        # 文件大小是警告，不阻止（exit 0）— 由 file_size_check.py 控制
    fi
fi

# G3: Secret scanning（所有文件改动时都检查）
echo "→ 运行 secret 扫描..."
SECRET_HITS=$(git diff --cached --name-only | while read f; do
    [ -f "$f" ] || continue
    # 跳过 .gitignore 中的文件
    git check-ignore "$f" 2>/dev/null && continue
    # 扫描常见密钥模式
    if grep -nE '(sk-[a-zA-Z0-9]{32,}|AKIA[A-Z0-9]{16}|ghp_[a-zA-Z0-9]{36}|eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+|-----BEGIN (RSA |EC )?PRIVATE KEY-----)' "$f" 2>/dev/null; then
        echo "$f"
    fi
done)

if [ -n "$SECRET_HITS" ]; then
    # 检查人工覆盖
    COMMIT_MSG_FILE="$(git rev-parse --git-dir)/COMMIT_EDITMSG"
    if [ -f "$COMMIT_MSG_FILE" ] && grep -q "\[MANUAL-OVERRIDE\]" "$COMMIT_MSG_FILE"; then
        echo "⚠️  [MANUAL-OVERRIDE] 检测到，跳过 secret 扫描。"
    else
        echo "❌ 检测到可能的密钥/凭证："
        echo "$SECRET_HITS"
        echo ""
        echo "提交被阻止。如确需提交（如测试 fixture），请在 commit message 中添加 [MANUAL-OVERRIDE]。"
        exit 1
    fi
fi
echo "✅ Secret 扫描通过"

# 3. 检查契约文件是否被修改（警告）
if git diff --cached --name-only | grep -qE "^butler/contracts/"; then
    echo "⚠️  WARNING: 契约层文件被修改"
    echo "   请确保已运行契约测试: python -m pytest tests/contracts/ -v"
    echo "   并确认所有 Port 实现已同步更新。"
fi

# 4. 检查 shim 文件是否被修改（警告）
SHIM_FILES=$(git diff --cached --name-only | grep -E "\.py$" || true | while read f; do
    if [ -f "$f" ] && head -5 "$f" 2>/dev/null | grep -q "Deprecated:"; then
        echo "$f"
    fi
done)

if [ -n "$SHIM_FILES" ]; then
    echo "⚠️  WARNING: 以下 shim 文件被修改："
    echo "$SHIM_FILES" | while read f; do echo "   - $f"; done
    echo "   shim 文件是向后兼容层，修改不会影响实际实现。"
    echo "   如需修改功能，请修改对应的包目录下的实际实现文件。"
fi

echo "== AI Guard: pre-commit 检查通过 =="
exit 0
