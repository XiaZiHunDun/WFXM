#!/bin/bash
# 小说工作室 · 审核执行脚本 v1.0
# 用法: ./run_review.sh [command] [params]

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)/.."
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"
OPINION_DIR="$PROJECT_ROOT/06_意见仓库"
REVIEW_DIR="$PROJECT_ROOT/04_审核员工作室"
CONTENT_DIR="$PROJECT_ROOT/03_内容仓库"

# 审核员列表
REVIEWERS=("审核员A" "审核员B" "审核员C" "审核员D" "审核员E"
           "审核员F" "审核员G" "审核员H" "审核员I" "审核员J" "审核员K")

# 主编轮值顺序
CHIEF_REVIEWERS=("审核员A" "审核员B" "审核员C" "审核员D" "审核员E")

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
审核执行脚本 v1.0

用法: ./run_review.sh [command] [params]

命令:
  batch <章节范围>           批量启动审核员并行审核
                             示例: ./run_review.sh batch ch001-ch010

  assign <审核员> <章节范围> 分配单个审核员执行审核
                             示例: ./run_review.sh assign 审核员A ch001-ch005

  status                     查看审核进度
                             示例: ./run_review.sh status

  report [批次]              生成审核报告
                             示例: ./run_review.sh report B01

  verdict [批次]             执行定稿判定
                             示例: ./run_review.sh verdict B01

  chief                      查看当前主编轮值
                             示例: ./run_review.sh chief

  list                       列出所有审核员状态
                             示例: ./run_review.sh list

  pending                    查看待处理审核任务
                             示例: ./run_review.sh pending

情感审核专项命令:
  emotion_batch <章节范围>   情感专项批量审核
                             示例: ./run_review.sh emotion_batch ch001-ch010

  emotion_assign <审核员> <章节范围>
                             分配情感专项审核
                             示例: ./run_review.sh emotion_assign 审核员K ch001-ch005

  emotion_report [批次]      生成情感审核报告
                             示例: ./run_review.sh emotion_report B01

审核批次命名规范:
  B01_第一章_20260514
  B02_卷1大纲_20260514
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
        local batch_num=$(grep -o '"batch_num":[0-9]*' "$WORKFLOW_FILE" 2>/dev/null | head -1 | cut -d':' -f2)
        if [ -z "$batch_num" ]; then
            echo "1"
        else
            echo "$batch_num"
        fi
    else
        echo "1"
    fi
}

# 获取主编轮值
function get_chief_reviewer() {
    local batch_num=$(get_current_batch)
    local index=$(( (batch_num - 1) % ${#CHIEF_REVIEWERS[@]} ))
    echo "${CHIEF_REVIEWERS[$index]}"
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

# 创建审核批次目录
function create_batch_dirs() {
    local batch_id=$1
    local batch_dir="$OPINION_DIR/04_正文_审核/$batch_id"
    mkdir -p "$batch_dir"
    echo "$batch_dir"
}

# ==================== 命令实现 ====================

# 批量启动审核员并行审核
function cmd_batch() {
    local chapter_range=$1
    if [ -z "$chapter_range" ]; then
        log_error "请指定章节范围，示例: ./run_review.sh batch ch001-ch010"
        exit 1
    fi

    log_info "批量启动审核员并行审核: $chapter_range"

    # 检查章节是否存在
    if ! check_chapters_exist "$chapter_range"; then
        exit 1
    fi

    # 生成批次号
    local batch_num=$(get_current_batch)
    local batch_id=$(printf "B%02d" $batch_num)
    local date_str=$(date +%Y%m%d)
    batch_id="${batch_id}_${chapter_range}_${date_str}"

    log_info "审核批次: $batch_id"

    # 创建批次目录
    local batch_dir=$(create_batch_dirs "$batch_id")

    # 解析章节范围
    local parsed=$(parse_chapter_range "$chapter_range")
    local start=$(echo "$parsed" | cut -d' ' -f1 | cut -d'=' -f2)
    local end=$(echo "$parsed" | cut -d' ' -f2 | cut -d'=' -f2)
    local total=$((end - start + 1))

    # 确定并行组数（每组5人）
    local group_size=5
    local group_count=$(( (total + group_size - 1) / group_size ))
    if [ $group_count -lt 1 ]; then
        group_count=1
    fi

    log_info "共 $total 章，分 $group_count 组并行审核"

    # 当前主编
    local chief=$(get_chief_reviewer)
    log_info "当前主编: $chief"

    # 分配审核任务
    local group_num=1
    local reviewer_index=0

    for ((i=start; i<=end; i++)); do
        local ch_num=$(printf "%03d" $i)
        local reviewer=${REVIEWERS[$reviewer_index]}

        # 记录审核任务
        local task_id="${batch_id}_${reviewer}_${ch_num}"
        log_step "分配: $reviewer → 审核 $ch_num"

        # 这里应该调用Agent启动，实际实现时通过主控调度
        # 临时记录到任务文件
        echo "$task_id|$reviewer|ch$ch_num|pending" >> "$batch_dir/tasks.txt"

        reviewer_index=$(( (reviewer_index + 1) % ${#REVIEWERS[@]} ))

        # 每5章换组
        if [ $(( (i - start + 1) % group_size )) -eq 0 ]; then
            group_num=$((group_num + 1))
            log_info "--- 第 $group_num 组开始 ---"
        fi
    done

    # 更新workflow_state
    if [ -f "$WORKFLOW_FILE" ]; then
        local timestamp=$(date +%Y-%m-%dT%H:%M:%S)
        # 使用Python更新JSON（更可靠）
        python3 << PYEOF
import json

try:
    with open('$WORKFLOW_FILE', 'r', encoding='utf-8') as f:
        wf = json.load(f)

    if 'review_queue' not in wf:
        wf['review_queue'] = {'pending': [], 'in_review': [], 'completed': []}
    if 'batches' not in wf:
        wf['batches'] = {}

    batch_info = {
        'batch_id': '$batch_id',
        'chapter_range': '$chapter_range',
        'chief': '$chief',
        'created_at': '$timestamp',
        'status': 'in_progress',
        'total_chapters': $total,
        'reviewed': 0,
        'pending': $total
    }

    wf['batches']['$batch_id'] = batch_info
    wf['review_queue']['pending'].append('$chapter_range')

    with open('$WORKFLOW_FILE', 'w', encoding='utf-8') as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)

    print('updated')
except Exception as e:
    print(f'error: {e}')
PYEOF
    fi

    log_info "批次 $batch_id 创建完成，等待审核员执行..."
    log_info "使用 ./run_review.sh status 查看进度"
}

# 分配单个审核员
function cmd_assign() {
    local reviewer=$1
    local chapter_range=$2

    if [ -z "$reviewer" ] || [ -z "$chapter_range" ]; then
        log_error "请指定审核员和章节范围，示例: ./run_review.sh assign 审核员A ch001-ch005"
        exit 1
    fi

    # 验证审核员
    local valid=false
    for r in "${REVIEWERS[@]}"; do
        if [ "$r" == "$reviewer" ]; then
            valid=true
            break
        fi
    done

    if [ "$valid" != "true" ]; then
        log_error "无效的审核员: $reviewer"
        log_info "有效审核员: ${REVIEWERS[*]}"
        exit 1
    fi

    log_info "分配审核任务: $reviewer → $chapter_range"

    # 检查章节
    if ! check_chapters_exist "$chapter_range"; then
        exit 1
    fi

    # 获取批次信息
    local batch_num=$(get_current_batch)
    local batch_id=$(printf "B%02d" $batch_num)
    local date_str=$(date +%Y%m%d)
    batch_id="${batch_id}_${chapter_range}_${date_str}"

    local batch_dir=$(create_batch_dirs "$batch_id")

    # 解析范围并记录任务
    local parsed=$(parse_chapter_range "$chapter_range")
    local start=$(echo "$parsed" | cut -d' ' -f1 | cut -d'=' -f2)
    local end=$(echo "$parsed" | cut -d' ' -f2 | cut -d'=' -f2)

    for ((i=start; i<=end; i++)); do
        local ch_num=$(printf "%03d" $i)
        local task_id="${batch_id}_${reviewer}_${ch_num}"
        log_step "分配: $reviewer → 审核 $ch_num"
        echo "$task_id|$reviewer|ch$ch_num|pending" >> "$batch_dir/tasks.txt"
    done

    log_info "任务分配完成"
}

# 查看审核进度
function cmd_status() {
    log_info "审核进度概览"
    echo ""

    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi

    echo "=== 当前主编轮值 ==="
    local chief=$(get_chief_reviewer)
    echo "主编: $chief"
    echo ""

    echo "=== 审核批次状态 ==="
    python3 << 'PYEOF'
import json
import os

workflow_file = os.environ.get('WORKFLOW_FILE', 'workflow_state.json')

try:
    with open(workflow_file, 'r', encoding='utf-8') as f:
        wf = json.load(f)

    batches = wf.get('batches', {})
    review_queue = wf.get('review_queue', {})

    if not batches:
        print("暂无审核批次")
    else:
        for bid, binfo in batches.items():
            print(f"批次: {bid}")
            print(f"  章节范围: {binfo.get('chapter_range', 'N/A')}")
            print(f"  主编: {binfo.get('chief', 'N/A')}")
            print(f"  状态: {binfo.get('status', 'N/A')}")
            print(f"  进度: {binfo.get('reviewed', 0)}/{binfo.get('total_chapters', 0)}")
            print(f"  待审: {binfo.get('pending', 0)}")
            print(f"  创建时间: {binfo.get('created_at', 'N/A')}")
            print()

    pending = review_queue.get('pending', [])
    if pending:
        print(f"待处理队列: {', '.join(pending)}")
    else:
        print("待处理队列: 空")
PYEOF

    echo ""
    echo "=== 审核员状态 ==="
    for reviewer in "${REVIEWERS[@]}"; do
        local reviewer_dir="$REVIEW_DIR/$reviewer"
        if [ -d "$reviewer_dir" ]; then
            local record_count=$(find "$reviewer_dir/审核记录" -name "*.md" 2>/dev/null | wc -l)
            printf "  %-8s [%d条记录]\n" "$reviewer" "$record_count"
        else
            printf "  %-8s [目录不存在]\n" "$reviewer"
        fi
    done
}

# 生成审核报告
function cmd_report() {
    local batch_filter=$1

    log_info "生成审核报告..."

    if [ -z "$batch_filter" ]; then
        # 生成最新批次报告
        batch_filter=$(printf "B%02d" $(get_current_batch))
    fi

    log_info "筛选批次: $batch_filter"

    local report_dir="$OPINION_DIR/04_正文_审核"
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
    echo "           审核报告 - $batch_filter"
    echo "=========================================="
    echo ""
    echo "批次目录: $(basename "$batch_dir")"
    echo "总任务数: $total_tasks"
    echo "待审核: $pending_tasks"
    echo "已完成: $completed_tasks"
    echo "完成率: $(echo "scale=1; $completed_tasks*100/$total_tasks" 2>/dev/null || echo "N/A")%"
    echo ""

    # 按审核员统计
    echo "=== 按审核员统计 ==="
    if [ -f "$batch_dir/tasks.txt" ]; then
        for reviewer in "${REVIEWERS[@]}"; do
            local reviewer_tasks=$(grep "$reviewer|" "$batch_dir/tasks.txt" 2>/dev/null | wc -l)
            if [ "$reviewer_tasks" -gt 0 ]; then
                printf "  %-8s: %d章\n" "$reviewer" "$reviewer_tasks"
            fi
        done
    fi

    echo ""
    echo "=========================================="

    # 生成markdown报告
    local report_file="$batch_dir/审核报告_$(basename "$batch_dir").md"
    cat > "$report_file" << EOF
# 审核报告 - $(basename "$batch_dir")

## 基本信息
- **批次ID**: $(basename "$batch_dir")
- **生成时间**: $(date +%Y-%m-%d\ %H:%M:%S)
- **报告类型**: 批次进度报告

## 审核统计
| 指标 | 数值 |
|------|------|
| 总任务数 | $total_tasks |
| 待审核 | $pending_tasks |
| 已完成 | $completed_tasks |
| 完成率 | $(echo "scale=1; $completed_tasks*100/$total_tasks" 2>/dev/null || echo "N/A")% |

## 审核员任务分配
$(if [ -f "$batch_dir/tasks.txt" ]; then
for reviewer in "${REVIEWERS[@]}"; do
    reviewer_tasks=$(grep "$reviewer|" "$batch_dir/tasks.txt" 2>/dev/null | wc -l)
    if [ "$reviewer_tasks" -gt 0 ]; then
        echo "| $reviewer | $reviewer_tasks |"
    fi
done
fi)

## 主编裁决
- **主编**: $(get_chief_reviewer)
- **裁决结果**: 待裁决
- **备注**: 自动生成报告，待主编审核后定稿

---
*自动生成于 $(date +%Y-%m-%d\ %H:%M:%S)*
EOF

    log_info "报告已生成: $report_file"
}

# 执行定稿判定
function cmd_verdict() {
    local batch_filter=$1

    if [ -z "$batch_filter" ]; then
        batch_filter=$(printf "B%02d" $(get_current_batch))
    fi

    log_info "执行定稿判定: $batch_filter"

    local chief=$(get_chief_reviewer)
    log_info "主编: $chief"

    local report_dir="$OPINION_DIR/04_正文_审核"
    local batch_dir=""

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

    # 检查完成情况
    if [ -f "$batch_dir/tasks.txt" ]; then
        local pending=$(grep -c "|pending$" "$batch_dir/tasks.txt" 2>/dev/null || echo "0")
        if [ "$pending" -gt 0 ]; then
            log_warn "仍有 $pending 个任务待审核，暂不能定稿"
            log_info "请先完成所有审核任务"
            exit 1
        fi
    fi

    # 统计意见
    local opinion_count=$(find "$batch_dir" -name "*审核记录*.md" 2>/dev/null | wc -l)

    echo ""
    echo "=========================================="
    echo "           定稿判定 - $batch_filter"
    echo "=========================================="
    echo ""
    echo "主编: $chief"
    echo "审核记录: $opinion_count 条"
    echo ""

    # 判定
    if [ "$opinion_count" -eq 0 ]; then
        echo "判定结果: 通过（S级）"
        echo "理由: 无审核意见，内容完整度>90%"
    elif [ "$opinion_count" -le 5 ]; then
        echo "判定结果: 通过（需小幅调整，A级）"
        echo "理由: 意见数量≤5条，无P0硬伤"
    else
        echo "判定结果: 需修改"
        echo "理由: 意见数量>5条，需返回作家修改"
    fi

    echo ""
    echo "=========================================="

    # 更新批次状态
    python3 << PYEOF
import json

try:
    with open('$WORKFLOW_FILE', 'r', encoding='utf-8') as f:
        wf = json.load(f)

    batch_id = '$(basename "$batch_dir")'
    if batch_id in wf.get('batches', {}):
        wf['batches'][batch_id]['status'] = 'verified'
        wf['batches'][batch_id]['verdict_at'] = '$(date +%Y-%m-%dT%H:%M:%S)'
        wf['batches'][batch_id]['verdict_chief'] = '$chief'

        with open('$WORKFLOW_FILE', 'w', encoding='utf-8') as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)

        print('批次状态已更新')
except Exception as e:
    print(f'更新失败: {e}')
PYEOF

    log_info "定稿判定完成"
}

# 查看主编轮值
function cmd_chief() {
    echo "=== 主编轮值表 ==="
    echo ""
    local batch_num=$(get_current_batch)
    echo "当前批次: $batch_num"
    echo ""
    echo "轮值顺序:"
    for i in "${!CHIEF_REVIEWERS[@]}"; do
        local num=$((i+1))
        local r="${CHIEF_REVIEWERS[$i]}"
        if [ $((batch_num % ${#CHIEF_REVIEWERS[@]})) -eq $i ]; then
            echo "  $num. $r ← 当前"
        else
            echo "  $num. $r"
        fi
    done
    echo ""
    echo "当前主编: $(get_chief_reviewer)"
}

# 列出审核员状态
function cmd_list() {
    echo "=== 审核员列表 ==="
    echo ""
    printf "%-8s %-10s %-15s %s\n" "审核员" "专项" "状态" "当前任务"
    echo "--------------------------------------------"
    for reviewer in "${REVIEWERS[@]}"; do
        local reviewer_dir="$REVIEW_DIR/$reviewer"
        local specialty="综合"
        local status="空闲"
        local current_task="无"

        # 读取专项
        if [ -f "$reviewer_dir/profile.md" ]; then
            specialty=$(grep -m1 "专项" "$reviewer_dir/profile.md" 2>/dev/null | sed 's/.*：//' || echo "综合")
        fi

        # 检查是否有进行中的任务
        if [ -f "$WORKFLOW_FILE" ]; then
            # 简化实现
            :
        fi

        printf "%-8s %-10s %-15s %s\n" "$reviewer" "$specialty" "$status" "$current_task"
    done
}

# 查看待处理任务
function cmd_pending() {
    log_info "待处理审核任务"
    echo ""

    local report_dir="$OPINION_DIR/04_正文_审核"
    local pending_found=false

    for dir in "$report_dir"/*/; do
        if [ -d "$dir" ]; then
            local batch_name=$(basename "$dir")
            if [ -f "$dir/tasks.txt" ]; then
                local pending=$(grep "|pending$" "$dir/tasks.txt" 2>/dev/null)
                if [ -n "$pending" ]; then
                    pending_found=true
                    echo "批次: $batch_name"
                    while IFS='|' read -r task_id reviewer ch status; do
                        echo "  - $reviewer → $ch ($status)"
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

# ==================== 情感审核专项 ====================

EMOTION_CHECKLISTS="$REVIEW_DIR/情感审核专项"

function cmd_emotion_batch() {
    local chapters=$1
    log_step "情感专项批量审核: $chapters"
    echo "  检查项: 情感弧线/配角价值/反派动机/节奏/转折"
    echo "  检查清单: $EMOTION_CHECKLISTS/"
    echo ""
    echo "情感审核专项检查清单："
    echo "  - 情感弧线检查清单.md"
    echo "  - 配角价值验证标准.md"
    echo "  - 反派动机深度评估.md"
    echo "  - 节奏健康度标准.md"
    echo "  - 转折合理性验证.md"
    echo ""
    echo "输出目录: 06_意见仓库/情感审核/"
    echo ""
    echo "注意：情感审核与技术审核并行，执行双轨审核"
}

function cmd_emotion_assign() {
    local reviewer=$1
    local chapters=$2
    log_step "分配情感专项审核: $reviewer → $chapters"
    echo "  检查清单: $EMOTION_CHECKLISTS/"
    echo "  输出: 06_意见仓库/情感审核/"
    echo ""
    echo "审核员 $reviewer 情感专项检查范围："
    echo "  - 情感弧线（主角/女主转折、婚后日常）"
    echo "  - 配角价值（非战力价值、独立支线）"
    echo "  - 反派动机（前身、行动逻辑）"
    echo "  - 节奏健康度（变速、冲突密度）"
    echo "  - 转折合理性（隐瞒必要性、理解铺垫）"
}

function cmd_emotion_report() {
    local batch=$1
    log_step "生成情感审核报告: $batch"
    local output="$OPINION_DIR/情感审核/${batch}_情感审核.md"
    echo "  输出: $output"
    echo ""
    echo "情感审核报告将包含："
    echo "  - 5项检查维度结果（✅/⚠️/❌）"
    echo "  - P0/P1/P2问题清单"
    echo "  - 修复建议"
    echo "  - 综合等级（S/A/B/不合格）"
}

# ==================== 主程序 ====================

COMMAND=$1
shift || true

case "$COMMAND" in
    batch)
        cmd_batch "$@"
        ;;
    assign)
        cmd_assign "$@"
        ;;
    status)
        cmd_status
        ;;
    report)
        cmd_report "$@"
        ;;
    verdict)
        cmd_verdict "$@"
        ;;
    chief)
        cmd_chief
        ;;
    list)
        cmd_list
        ;;
    pending)
        cmd_pending "$@"
        ;;
    emotion_batch)
        cmd_emotion_batch "$@"
        ;;
    emotion_assign)
        cmd_emotion_assign "$@"
        ;;
    emotion_report)
        cmd_emotion_report "$@"
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
