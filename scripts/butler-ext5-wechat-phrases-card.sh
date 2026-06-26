#!/usr/bin/env bash
# Print EXT-5 + Owner 首周 WeChat phrases for copy-paste (真机验收).
#
# Usage:
#   bash scripts/butler-ext5-wechat-phrases-card.sh
#   bash scripts/butler-ext5-wechat-phrases-card.sh --ext5-only
#
set -euo pipefail

EXT5_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --ext5-only) EXT5_ONLY=1 ;;
  esac
done

cat <<'EOF'
=== EXT-5 微信真机话术（逐条复制发送）===

【准备】
/切换 灵文1号

【#1 诊断】
/诊断 详细
→ 期望：.txt 附件含 markitdown (stdio) [ok]、markitdown-ingest [ok]

【#2 TXT→MD】
把 docs/ext5-fixture-sample.txt 转成 Markdown

【#3 进记忆 — 二选一】
(有 PDF) 先发 PDF 附件，再发：
把这份 PDF 转成 Markdown 放进记忆

(无 PDF) 直接发：
把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆

【#4 参考书路径】
用 MarkItDown 转换项目里的参考书 docs/ext5-fixture-sample.txt

EOF

if [[ "$EXT5_ONLY" -eq 0 ]]; then
  cat <<'EOF'
【Owner 首周 · 可选】
/简报

/反馈 真机验收：EXT-5 话术卡走通

EOF
fi

cat <<'EOF'
【结案 SSH】
bash scripts/butler-extension-verify.sh markitdown-ingest

详版：docs/guides/ext5-wechat-phrases-card-2026-06.md
EOF
