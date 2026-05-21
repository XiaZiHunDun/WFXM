#!/bin/bash
# 小说工作室 · 作家执行脚本 v1.0
# 用法: ./run_writer.sh [command] [params]

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)/.."
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"
OPINION_DIR="$PROJECT_ROOT/06_意见仓库"
WRITER_DIR="$PROJECT_ROOT/02_作家工作室"
CONTENT_DIR="$PROJECT_ROOT/03_内容仓库"

# 作家列表
WRITERS=("作家A" "作家B" "作家C" "作家D" "作家E"
         "作家F" "作家G" "作家H" "作家I" "作家J")

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
function log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
function log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
function log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# ==================== 帮助信息 ====================

function show_help() {
    cat << 'EOF'
作家执行脚本 v1.0

用法: ./run_writer.sh [command] [params]

命令:
  assign <作家> <章节>      分配单章修改任务
                            示例: ./run_writer.sh assign 作家A ch001

  batch <章节范围>          批量启动10作家并行修改
                            示例: ./run_writer.sh batch ch001-ch010

  status                    查看修改进度
                            示例: ./run_writer.sh status

  report [批次]             生成修改报告
                            示例: ./run_writer.sh report W01

  pending                   查看待处理修改任务
                            示例: ./run_writer.sh pending

  list                      列出所有作家状态
                            示例: ./run_writer.sh list

  chief                     查看当前主编轮值
                            示例: ./run_writer.sh chief

批次命名规范:
  W01_ch001-ch010_20260514
  W02_ch011-ch020_20260514
EOF
}

# ==================== 工具函数 ====================

# 解析章节范围
function parse_chapter_range() {
    local range=$1
    if [[ $range =~ ^ch([0-9]+)-ch([0-9]+)$ ]]; then
        local start=${BASH_REMATCH[1]}
        local end=${BASH_REMATCH[2]}
        echo "start=$start end=$end"
    else
        echo "invalid"
    fi
}

# 获取当前批次号
function get_current_batch() {
    if [ -f "$WORKFLOW_FILE" ]; then
        local batch_num=$(grep -o '"writer_batch_num":[0-9]*' "$WORKFLOW_FILE" 2>/dev/null | head -1 | cut -d':' -f2)
        if [ -z "$batch_num" ]; then
            echo "1"
        else
            echo "$batch_num"
        fi
    else
        echo "1"
    fi
}

# 检查章节文件是否存在
function check_chapters_exist() {
    local range=$1
    local parsed=$(parse_chapter_range "$range")
    if [ "$parsed" == "invalid" ]; then
        log_error "无效的章节范围: $range，格式应为 ch001-ch010"
        return 1
    fi

    local start=$(echo "$parsed" | cut -d' ' -f1 | cut -d'=' -f2)
    local end=$(echo "$parsed" | cut -d' ' -f2 | cut -d'=' -f2)

    local missing=""
    for ((i=start; i<=end; i++)); do
        local ch_num=$(printf "%03d" $i)
        local ch_file="$CONTENT_DIR/04_正文/ch${ch_num}.md"
        if [ ! -f "$ch_file" ]; then
            missing="$missing ch${ch_num}"
        fi
    done

    if [ -n "$missing" ]; then
        log_error "以下章节文件不存在:$missing"
        return 1
    fi
    return 0
}

# 创建修改批次目录
function create_batch_dirs() {
    local batch_id=$1
    local batch_dir="$OPINION_DIR/05_作家修改/$batch_id"
    mkdir -p "$batch_dir"
    echo "$batch_dir"
}

# ==================== 命令实现 ====================

# 分配单章修改任务
function cmd_assign() {
    local writer=$1
    local chapter=$2

    if [ -z "$writer" ] || [ -z "$chapter" ]; then
        log_error "请指定作家和章节，示例: ./run_writer.sh assign 作家A ch001"
        exit 1
    fi

    # 验证作家
    local valid=false
    for w in "${WRITERS[@]}"; do
        if [ "$w" == "$writer" ]; then
            valid=true
            break
        fi
    done

    if [ "$valid" != "true" ]; then
        log_error "无效的作家: $writer"
        log_info "有效作家: ${WRITERS[*]}"
        exit 1
    fi

    # 验证章节格式
    if [[ ! $chapter =~ ^ch[0-9]+$ ]]; then
        log_error "无效的章节格式: $chapter，格式应为 ch001"
        exit 1
    fi

    log_info "分配修改任务: $writer → $chapter"

    # 检查章节是否存在
    local ch_file="$CONTENT_DIR/04_正文/${chapter}.md"
    if [ ! -f "$ch_file" ]; then
        log_error "章节文件不存在: $ch_file"
        exit 1
    fi

    # 获取当前批次
    local batch_num=$(get_current_batch)
    local batch_id=$(printf "W%02d" $batch_num)
    local date_str=$(date +%Y%m%d)
    batch_id="${batch_id}_${chapter}_${date_str}"

    local batch_dir=$(create_batch_dirs "$batch_id")

    # 记录任务
    local task_id="${batch_id}_${writer}_${chapter}"
    log_step "分配: $writer → 修改 $chapter"
    echo "$task_id|$writer|$chapter|pending" >> "$batch_dir/tasks.txt"

    # 更新workflow_state
    if [ -f "$WORKFLOW_FILE" ]; then
        python3 << PYEOF
import json

try:
    with open('$WORKFLOW_FILE', 'r', encoding='utf-8') as f:
        wf = json.load(f)

    if 'writer_tasks' not in wf:
        wf['writer_tasks'] = {}

    task_key = '${writer}_${chapter}'
    wf['writer_tasks'][task_key] = {
        'task_id': '$task_id',
        'writer': '$writer',
        'chapter': '$chapter',
        'batch_id': '$batch_id',
        'status': 'pending',
        'assigned_at': '$(date +%Y-%m-%dT%H:%M:%S)'
    }

    with open('$WORKFLOW_FILE', 'w', encoding='utf-8') as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)

    print('updated')
except Exception as e:
    print(f'error: {e}')
PYEOF
    fi

    log_info "任务分配完成: $writer → $chapter"
}

# 批量启动10作家并行修改
function cmd_batch() {
    local chapter_range=$1
    if [ -z "$chapter_range" ]; then
        log_error "请指定章节范围，示例: ./run_writer.sh batch ch001-ch010"
        exit 1
    fi

    log_info "批量启动10作家并行修改: $chapter_range"

    # 检查章节是否存在
    if ! check_chapters_exist "$chapter_range"; then
        exit 1
    fi

    # 解析章节范围
    local parsed=$(parse_chapter_range "$chapter_range")
    local start=$(echo "$parsed" | cut -d' ' -f1 | cut -d'=' -f2)
    local end=$(echo "$parsed" | cut -d' ' -f2 | cut -d'=' -f2)
    local total=$((end - start + 1))

    # 检查是否为10的倍数
    if [ $total -ne 10 ]; then
        log_warn "注意：批量修改通常应为10章一批，当前为 $total 章"
    fi

    # 生成批次号
    local batch_num=$(get_current_batch)
    local batch_id=$(printf "W%02d" $batch_num)
    local date_str=$(date +%Y%m%d)
    batch_id="${batch_id}_${chapter_range}_${date_str}"

    log_info "修改批次: $batch_id"

    # 创建批次目录
    local batch_dir=$(create_batch_dirs "$batch_id")

    log_info "共 $total 章，启动 $total 个作家并行修改"

    # 分配任务 - 每章一个作家，循环使用
    local writer_index=0
    local ch_num=$start

    for ((i=start; i<=end; i++)); do
        local ch_formatted=$(printf "%03d" $i)
        local writer=${WRITERS[$writer_index]}

        # 记录任务
        local task_id="${batch_id}_${writer}_ch${ch_formatted}"
        log_step "分配: $writer → 修改 ch${ch_formatted}"

        echo "$task_id|$writer|ch${ch_formatted}|pending" >> "$batch_dir/tasks.txt"

        writer_index=$(( (writer_index + 1) % ${#WRITERS[@]} ))
    done

    # 更新workflow_state
    if [ -f "$WORKFLOW_FILE" ]; then
        local timestamp=$(date +%Y-%m-%dT%H:%M:%S)
        python3 << PYEOF
import json

try:
    with open('$WORKFLOW_FILE', 'r', encoding='utf-8') as f:
        wf = json.load(f)

    if 'writer_batches' not in wf:
        wf['writer_batches'] = {}

    batch_info = {
        'batch_id': '$batch_id',
        'chapter_range': '$chapter_range',
        'created_at': '$timestamp',
        'status': 'in_progress',
        'total_chapters': $total,
        'modified': 0,
        'pending': $total
    }

    wf['writer_batches']['$batch_id'] = batch_info
    wf['writer_batch_num'] = $batch_num + 1

    with open('$WORKFLOW_FILE', 'w', encoding='utf-8') as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)

    print('updated')
except Exception as e:
    print(f'error: {e}')
PYEOF
    fi

    log_info "批次 $batch_id 创建完成，$total 个作家已并行启动"
    log_info "使用 ./run_writer.sh status 查看进度"
}

# 查看修改进度
function cmd_status() {
    log_info "作家修改进度概览"
    echo ""

    echo "=== 作家状态 ==="
    printf "%-8s %-12s %-10s %s\n" "作家" "负责章节" "状态" "当前任务"
    echo "------------------------------------------------------------"

    for writer in "${WRITERS[@]}"; do
        local writer_dir="$WRITER_DIR/$writer"
        local current_chapters="未分配"
        local status="空闲"
        local current_task="无"

        # 检查进行中的任务
        if [ -f "$WORKFLOW_FILE" ]; then
            :
        fi

        printf "%-8s %-12s %-10s %s\n" "$writer" "$current_chapters" "$status" "$current_task"
    done

    echo ""

    # 显示当前批次
    echo "=== 修改批次状态 ==="
    if [ -f "$WORKFLOW_FILE" ]; then
        python3 << 'PYEOF'
import json
import os

workflow_file = os.environ.get('WORKFLOW_FILE', 'workflow_state.json')

try:
    with open(workflow_file, 'r', encoding='utf-8') as f:
        wf = json.load(f)

    batches = wf.get('writer_batches', {})

    if not batches:
        print("暂无修改批次")
    else:
        for bid, binfo in batches.items():
            print(f"批次: {bid}")
            print(f"  章节范围: {binfo.get('chapter_range', 'N/A')}")
            print(f"  状态: {binfo.get('status', 'N/A')}")
            print(f"  进度: {binfo.get('modified', 0)}/{binfo.get('total_chapters', 0)}")
            print(f"  待修改: {binfo.get('pending', 0)}")
            print()
PYEOF
    else
        echo "工作流文件不存在"
    fi
}

# 生成修改报告
function cmd_report() {
    local batch_filter=$1

    log_info "生成修改报告..."

    if [ -z "$batch_filter" ]; then
        batch_filter=$(printf "W%02d" $(get_current_batch))
    fi

    log_info "筛选批次: $batch_filter"

    local report_dir="$OPINION_DIR/05_作家修改"
    local batch_dir=""

    # 查找对应批次
    for dir in "$report_dir"/*; do
        if [ -d "$dir" ] && [[ $(basename "$dir") == *"$batch_filter"* ]]; then
            batch_dir="$dir"
            break
        fi
    done

    if [ -z "$batch_dir" ] || [ ! -d "$batch_dir" ]; then
        log_error "未找到批次: $batch_filter"
        exit 1
    fi

    log_info "批次目录: $batch_dir"

    # 统计任务
    local total_tasks=0
    local pending_tasks=0
    local completed_tasks=0

    if [ -f "$batch_dir/tasks.txt" ]; then
        total_tasks=$(wc -l < "$batch_dir/tasks.txt")
        pending_tasks=$(grep -c "|pending$" "$batch_dir/tasks.txt" 2>/dev/null || echo "0")
        completed_tasks=$(grep -c "|completed$" "$batch_dir/tasks.txt" 2>/dev/null || echo "0")
    fi

    echo ""
    echo "=========================================="
    echo "           修改报告 - $batch_filter"
    echo "=========================================="
    echo ""
    echo "批次目录: $(basename "$batch_dir")"
    echo "总任务数: $total_tasks"
    echo "待修改: $pending_tasks"
    echo "已完成: $completed_tasks"
    echo "完成率: $(echo "scale=1; $completed_tasks*100/$total_tasks" 2>/dev/null || echo "N/A")%"
    echo ""

    # 按作家统计
    echo "=== 按作家统计 ==="
    if [ -f "$batch_dir/tasks.txt" ]; then
        for writer in "${WRITERS[@]}"; do
            local writer_tasks=$(grep "$writer|" "$batch_dir/tasks.txt" 2>/dev/null | wc -l)
            if [ "$writer_tasks" -gt 0 ]; then
                printf "  %-8s: %d章\n" "$writer" "$writer_tasks"
            fi
        done
    fi

    echo ""
    echo "=========================================="

    # 生成markdown报告
    local report_file="$batch_dir/修改报告_$(basename "$batch_dir").md"
    cat > "$report_file" << EOF
# 修改报告 - $(basename "$batch_dir")

## 基本信息
- **批次ID**: $(basename "$batch_dir")
- **生成时间**: $(date +%Y-%m-%d\ %H:%M:%S)
- **报告类型**: 作家修改进度报告

## 修改统计
| 指标 | 数值 |
|------|------|
| 总任务数 | $total_tasks |
| 待修改 | $pending_tasks |
| 已完成 | $completed_tasks |
| 完成率 | $(echo "scale=1; $completed_tasks*100/$total_tasks" 2>/dev/null || echo "N/A")% |

## 作家任务分配
| 作家 | 任务数 |
|------|--------|
$(if [ -f "$batch_dir/tasks.txt" ]; then
for writer in "${WRITERS[@]}"; do
    writer_tasks=$(grep "$writer|" "$batch_dir/tasks.txt" 2>/dev/null | wc -l)
    if [ "$writer_tasks" -gt 0 ]; then
        echo "| $writer | $writer_tasks |"
    fi
done
fi)

## 修改完成报告
- **主编**: 作家主编
- **状态**: 待复审

---
*自动生成于 $(date +%Y-%m-%d\ %H:%M:%S)*
EOF

    log_info "报告已生成: $report_file"
}

# 查看待处理修改任务
function cmd_pending() {
    log_info "待处理修改任务"
    echo ""

    local report_dir="$OPINION_DIR/05_作家修改"
    local pending_found=false

    for dir in "$report_dir"/*/; do
        if [ -d "$dir" ]; then
            local batch_name=$(basename "$dir")
            if [ -f "$dir/tasks.txt" ]; then
                local pending=$(grep "|pending$" "$dir/tasks.txt" 2>/dev/null)
                if [ -n "$pending" ]; then
                    pending_found=true
                    echo "批次: $batch_name"
                    while IFS='|' read -r task_id writer ch status; do
                        echo "  - $writer → $ch ($status)"
                    done <<< "$pending"
                    echo ""
                fi
            fi
        fi
    done

    if [ "$pending_found" != "true" ]; then
        log_info "暂无待处理任务"
    fi
}

# 列出作家状态
function cmd_list() {
    echo "=== 作家列表 ==="
    echo ""
    printf "%-8s %-10s %-15s %s\n" "作家" "专项" "状态" "当前任务"
    echo "--------------------------------------------"
    for writer in "${WRITERS[@]}"; do
        local writer_dir="$WRITER_DIR/$writer"
        local specialty="综合"
        local status="空闲"
        local current_task="无"

        # 读取专项
        if [ -f "$writer_dir/profile.md" ]; then
            specialty=$(grep -m1 "专项" "$writer_dir/profile.md" 2>/dev/null | sed 's/.*：//' || echo "综合")
        fi

        printf "%-8s %-10s %-15s %s\n" "$writer" "$specialty" "$status" "$current_task"
    done
}

# 查看主编轮值
function cmd_chief() {
    echo "=== 作家主编轮值 ==="
    echo ""
    echo "主编由作家A-J中轮值选出"
    echo ""
    echo "当前主编: 作家主编（统筹）"
    echo ""
    echo "主编职责:"
    echo "  - 任务分配、进度监控、跨阶段协调"
    echo "  - 格式检查（不做质量评分）"
    echo "  - 向主控汇报进度"
}

# ==================== 主程序 ====================

COMMAND=$1
shift || true

case "$COMMAND" in
    assign)
        cmd_assign "$@"
        ;;
    batch)
        cmd_batch "$@"
        ;;
    status)
        cmd_status
        ;;
    report)
        cmd_report "$@"
        ;;
    pending)
        cmd_pending
        ;;
    list)
        cmd_list
        ;;
    chief)
        cmd_chief
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -n "$COMMAND" ]; then
            log_error "未知命令: $COMMAND"
        fi
        show_help
        exit 1
        ;;
esac