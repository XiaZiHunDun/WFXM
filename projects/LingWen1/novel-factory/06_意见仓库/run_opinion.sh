#!/bin/bash
# 意见仓库管理脚本 v1.0
# 用法: ./run_opinion.sh [command] [params]

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)/.."
OPINION_DIR="$PROJECT_ROOT/06_意见仓库"
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"

# 意见类型目录映射
declare -A TYPE_DIRS=(
    ["outline"]="01_全文大纲_审核"
    ["volume"]="02_卷大纲_审核"
    ["stage"]="03_阶段大纲_审核"
    ["content"]="04_正文_审核"
    ["writer"]="05_作家修改"
    ["reader"]="05_读者评论"
    ["summary"]="06_汇总_审核"
)

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
function log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
function log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
function log_section() { echo -e "${BLUE}=== $1 ===${NC}"; }

# 检查jq是否可用
JQ_AVAILABLE=false
if command -v jq > /dev/null 2>&1; then
    JQ_AVAILABLE=true
fi

# jq封装（如果没有jq则使用Python fallback）
function jq_get() {
    local key=$1
    local fallback=${2:-""}
    if [ "$JQ_AVAILABLE" = true ]; then
        local val=$(jq -r "$key" "$WORKFLOW_FILE" 2>/dev/null)
        if [ -n "$val" ] && [ "$val" != "null" ]; then
            echo "$val"
        else
            echo "$fallback"
        fi
    else
        local py_script=$(mktemp)
        echo 'import json, sys' > "$py_script"
        echo "wf = '$WORKFLOW_FILE'" >> "$py_script"
        echo "key = '$key'" >> "$py_script"
        echo "fallback = '$fallback'" >> "$py_script"
        cat >> "$py_script" << 'PYEOF'
try:
    with open(wf, encoding='utf-8') as f:
        data = json.load(f)
    val = data
    for k in key.split('.'):
        if k == '':
            continue
        if k.isdigit():
            val = val[int(k)]
        else:
            val = val[k]
    print(val if val is not None else fallback)
except Exception as e:
    print(fallback)
PYEOF
        python3 "$py_script" 2>/dev/null
        rm -f "$py_script"
    fi
}

# ==================== 帮助信息 ====================

function show_help() {
    cat << 'EOF'
意见仓库管理脚本 v1.0

用法: ./run_opinion.sh [command] [params]

命令:
  list <类型>       列出意见清单
                    类型: outline/volume/stage/content/writer/reader/summary/all

  pending          显示待处理意见（按优先级排序）

  assign <章节> <处理人>  分配意见处理
                    示例: ./run_opinion.sh assign ch001 作家A

  resolve <意见ID>  标记意见已解决
                    示例: ./run_opinion.sh resolve ch001_P0_001

  report           生成意见汇总报告

示例:
  ./run_opinion.sh list content    # 列出正文审核意见
  ./run_opinion.sh pending         # 查看待处理意见
  ./run_opinion.sh assign ch001 作家A  # 分配ch001给作家A处理
  ./run_opinion.sh resolve ch001_P0_001  # 标记意见已解决
  ./run_opinion.sh report          # 生成汇总报告
EOF
}

# ==================== 列表命令 ====================

function cmd_list() {
    local type=${1:-"all"}

    if [ "$type" = "all" ]; then
        log_section "全部意见清单"
        for t in outline volume stage content writer reader summary; do
            local dir="${TYPE_DIRS[$t]}"
            if [ -d "$OPINION_DIR/$dir" ]; then
                echo -e "\n${YELLOW}=== $t ($dir) ===${NC}"
                ls -1 "$OPINION_DIR/$dir/" 2>/dev/null | head -20
            fi
        done
    else
        local dir="${TYPE_DIRS[$type]}"
        if [ -z "$dir" ]; then
            log_error "未知类型: $type"
            echo "可用类型: outline, volume, stage, content, writer, reader, summary, all"
            exit 1
        fi

        log_section "$type 意见清单 ($dir)"
        local full_path="$OPINION_DIR/$dir"

        if [ ! -d "$full_path" ]; then
            log_warn "目录不存在: $full_path"
            exit 0
        fi

        echo -e "\n文件列表:"
        ls -1 "$full_path/" | while read f; do
            echo "  - $f"
        done

        echo -e "\n统计:"
        echo "  总文件数: $(ls -1 "$full_path/" | wc -l)"
    fi
}

# ==================== 待处理意见 ====================

function cmd_pending() {
    log_section "待处理意见汇总"

    local pending_count=0
    local p0_count=0
    local p1_count=0
    local p2_count=0
    local p3_count=0

    echo -e "\n${YELLOW}【P0 - 紧急】${NC}"
    for dir in "$OPINION_DIR"/*/; do
        grep -l "P0" "$dir"*.md 2>/dev/null | while read f; do
            local filename=$(basename "$f")
            local content=$(grep -A2 "P0" "$f" | head -5)
            echo "  $filename"
            echo "    $(echo "$content" | head -1)"
            ((p0_count++))
        done
    done
    [ $p0_count -eq 0 ] && echo "  (无)"

    echo -e "\n${YELLOW}【P1 - 高优】${NC}"
    for dir in "$OPINION_DIR"/*/; do
        grep -l "P1" "$dir"*.md 2>/dev/null | head -10 | while read f; do
            local filename=$(basename "$f")
            local content=$(grep -A2 "P1" "$f" | head -3)
            echo "  $filename"
            echo "    $(echo "$content" | head -1)"
            ((p1_count++))
        done
    done
    [ $p1_count -eq 0 ] && echo "  (无)"

    echo -e "\n${YELLOW}【P2 - 中优】${NC}"
    for dir in "$OPINION_DIR"/*/; do
        grep -l "P2" "$dir"*.md 2>/dev/null | head -10 | while read f; do
            local filename=$(basename "$f")
            echo "  $filename"
            ((p2_count++))
        done
    done
    [ $p2_count -eq 0 ] && echo "  (无)"

    echo -e "\n${YELLOW}【P3 - 低优】${NC}"
    for dir in "$OPINION_DIR"/*/; do
        grep -l "P3" "$dir"*.md 2>/dev/null | head -10 | while read f; do
            local filename=$(basename "$f")
            echo "  $filename"
            ((p3_count++))
        done
    done 2>/dev/null
    [ $p3_count -eq 0 ] && echo "  (无)"

    pending_count=$((p0_count + p1_count + p2_count + p3_count))

    echo -e "\n${BLUE}=== 统计汇总 ===${NC}"
    echo "  P0 (紧急): $p0_count"
    echo "  P1 (高优): $p1_count"
    echo "  P2 (中优): $p2_count"
    echo "  P3 (低优): $p3_count"
    echo "  ----------------"
    echo "  待处理总计: $pending_count"
}

# ==================== 分配意见 ====================

function cmd_assign() {
    local chapter=${1:-""}
    local handler=${2:-""}

    if [ -z "$chapter" ] || [ -z "$handler" ]; then
        log_error "参数不足"
        echo "用法: ./run_opinion.sh assign <章节> <处理人>"
        echo "示例: ./run_opinion.sh assign ch001 作家A"
        exit 1
    fi

    log_info "分配意见处理: $chapter -> $handler"

    # 查找对应的意见文件
    local found=false
    for dir in "$OPINION_DIR"/*/; do
        local pattern="${chapter}_*审核*.md"
        local matches=$(ls "$dir" 2>/dev/null | grep -E "ch[0-9]+.*审核.*\.md$" | grep -i "$chapter" | head -1)
        if [ -n "$matches" ]; then
            echo "  找到意见文件: $matches"
            echo "  分配给: $handler"
            found=true
            break
        fi
    done

    if [ "$found" = false ]; then
        log_warn "未找到章节 $chapter 的审核意见"
        log_info "将创建分配记录..."

        # 创建分配记录
        local assign_file="$OPINION_DIR/assignment_log.md"
        echo "- $(date '+%Y-%m-%d %H:%M:%S') | $chapter | -> $handler" >> "$assign_file"
        log_info "已记录分配"
    fi
}

# ==================== 标记解决 ====================

function cmd_resolve() {
    local opinion_id=${1:-""}

    if [ -z "$opinion_id" ]; then
        log_error "参数不足"
        echo "用法: ./run_opinion.sh resolve <意见ID>"
        echo "示例: ./run_opinion.sh resolve ch001_P0_001"
        exit 1
    fi

    log_info "标记意见已解决: $opinion_id"

    # 解析意见ID (格式: chXXX_PX_XXX)
    local chapter=$(echo "$opinion_id" | grep -oE "ch[0-9]+")
    local priority=$(echo "$opinion_id" | grep -oE "P[0-3]")
    local seq=$(echo "$opinion_id" | grep -oE "_[0-9]+$")

    if [ -z "$chapter" ]; then
        log_error "无法解析意见ID: $opinion_id"
        echo "格式应为: chXXX_PX_XXX (如: ch001_P0_001)"
        exit 1
    fi

    # 查找并标记
    local found=false
    for dir in "$OPINION_DIR"/*/; do
        local pattern="${chapter}_*审核*.md"
        local matches=$(ls "$dir" 2>/dev/null | grep -E "ch[0-9]+.*审核.*\.md$" | grep -i "$chapter" | head -1)
        if [ -n "$matches" ]; then
            local full_path="$dir/$matches"
            echo -e "\n  找到文件: $full_path"

            # 检查是否已有解决标记
            if grep -q "## 解决状态" "$full_path"; then
                # 更新现有状态
                sed -i "s/| $priority.*/| $priority | 已解决 | $(date '+%Y-%m-%d') |/" "$full_path"
            else
                # 添加解决状态节
                echo -e "\n## 解决状态\n\n| 优先级 | 状态 | 解决时间 |" >> "$full_path"
                echo "| $priority | 已解决 | $(date '+%Y-%m-%d') |" >> "$full_path"
            fi

            echo "  已标记为已解决"
            found=true
            break
        fi
    done

    if [ "$found" = false ]; then
        log_warn "未找到意见: $opinion_id"
        log_info "创建解决记录..."

        local resolve_file="$OPINION_DIR/resolved_log.md"
        echo "- $(date '+%Y-%m-%d %H:%M:%S') | $opinion_id | resolved" >> "$resolve_file"
        log_info "已记录解决"
    fi
}

# ==================== 生成报告 ====================

function cmd_report() {
    log_section "意见汇总报告"
    echo "生成时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # 统计各目录意见数
    echo -e "${BLUE}=== 各类型意见统计 ===${NC}"
    local total=0
    for dir in "$OPINION_DIR"/*/; do
        local dirname=$(basename "$dir")
        local count=$(ls -1 "$dir" 2>/dev/null | wc -l)
        echo "  $dirname: $count"
        total=$((total + count))
    done
    echo "  ----------------"
    echo "  总计: $total"
    echo ""

    # 按优先级统计
    echo -e "${BLUE}=== 优先级分布 ===${NC}"
    local p0=$(grep -r "P0" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local p1=$(grep -r "P1" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local p2=$(grep -r "P2" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local p3=$(grep -r "P3" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    echo "  P0 (紧急): $p0"
    echo "  P1 (高优): $p1"
    echo "  P2 (中优): $p2"
    echo "  P3 (低优): $p3"
    echo ""

    # 最近的审核文件
    echo -e "${BLUE}=== 最近审核文件 (Top 10) ===${NC}"
    find "$OPINION_DIR" -name "*.md" -type f -mtime -7 2>/dev/null | \
        xargs ls -lt 2>/dev/null | head -10 | \
        while read line; do
            echo "  $line"
        done
    echo ""

    # 问题类型分布
    echo -e "${BLUE}=== 问题类型分布 ===${NC}"
    local logic=$(grep -r "逻辑" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local character=$(grep -r "人设\|角色" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local plot=$(grep -r "节奏\|情节" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local setting=$(grep -r "设定\|世界观" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    local style=$(grep -r "风格\|文笔" "$OPINION_DIR" --include="*.md" 2>/dev/null | wc -l)
    echo "  逻辑问题: $logic"
    echo "  人设问题: $character"
    echo "  节奏/情节: $plot"
    echo "  设定/世界观: $setting"
    echo "  风格/文笔: $style"
    echo ""

    echo -e "${GREEN}报告生成完成${NC}"
}

# ==================== 主入口 ====================

case "${1:-}" in
    list)
        cmd_list "$2"
        ;;
    pending)
        cmd_pending
        ;;
    assign)
        cmd_assign "$2" "$3"
        ;;
    resolve)
        cmd_resolve "$2"
        ;;
    report)
        cmd_report
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -z "$1" ]; then
            show_help
            exit 0
        else
            log_error "未知命令: $1"
            show_help
            exit 1
        fi
        ;;
esac
