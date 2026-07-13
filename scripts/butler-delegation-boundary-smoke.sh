#!/usr/bin/env bash
# P1 #4 — content vs dev 委派边界 smoke
# 真跑四个 case：content→src 拒绝 / dev→docs 拒绝 / content→docs 放行 / no-role passthrough
set -e
cd "$(dirname "$0")/.."

RED=$'\e[31m'; GREEN=$'\e[32m'; RESET=$'\e[0m'

# 用临时文件捕 stderr，避免污染 stdout；用 PIPESTATUS[1] 捕 python 退出码
TMPDIR_SMOKE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_SMOKE"' EXIT

run_case() {
    local label="$1" role="$2" path="$3" expected="$4"
    set +e
    echo "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$path\"}}" \
        | BUTLER_AGENT_ROLE="$role" BUTLER_ACTIVE_PROJECT="LingWen1" \
            /home/ailearn/miniconda3/bin/python3 -m butler.hooks.delegation_boundary_hook \
            > "$TMPDIR_SMOKE/out" 2> "$TMPDIR_SMOKE/err"
    local actual=${PIPESTATUS[1]}
    set -e
    if [[ "$actual" == "$expected" ]]; then
        echo "${GREEN}PASS${RESET} $label: exit=$actual"
    else
        echo "${RED}FAIL${RESET} $label: expected=$expected actual=$actual"
        echo "  stderr: $(cat "$TMPDIR_SMOKE/err")"
        exit 1
    fi
}

run_case "content→src (deny)"   content "src/butler/poison.py"             2
run_case "dev→docs (deny)"      dev    "projects/灵文1号/docs/poison.md"  2
run_case "content→docs (allow)" content "projects/灵文1号/docs/x.md"       0
run_case "no-role (passthrough)" ""    "projects/灵文1号/docs/x.md"       0

echo "${GREEN}ALL PASS${RESET}: delegation boundary smoke"