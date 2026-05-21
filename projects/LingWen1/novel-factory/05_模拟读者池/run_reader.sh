#!/bin/bash
# ============================================
# 读者部门调度脚本
# ============================================
# 功能：
#   - assign: 分配阅读任务给指定读者
#   - batch: 批量启动读者并行阅读
#   - status: 查看当前阅读进度
#   - report: 生成读者评论汇总
# ============================================

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
NOVEL_FACTORY="$SCRIPT_DIR"
READER_POOL="$NOVEL_FACTORY/05_模拟读者池"
OPINIONS="$NOVEL_FACTORY/06_意见仓库/03_正文_读者评论"
CONTENT_STORE="$NOVEL_FACTORY/03_内容仓库/04_正文"

# 读者列表
READERS=("读者A" "读者B" "读者C" "读者D" "读者E" "读者F" "读者G" "读者H" "读者I" "读者J"
         "读者K" "读者L" "读者M" "读者N" "读者O" "读者P" "读者Q" "读者R" "读者S" "读者T")

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助
show_help() {
    echo "==========================================="
    echo "         读者部门调度脚本"
    echo "==========================================="
    echo ""
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  assign <读者> <章节范围>  分配阅读任务给指定读者"
    echo "     示例: $0 assign 读者A ch001-ch010"
    echo ""
    echo "  batch <章节范围>         批量启动读者并行阅读"
    echo "     示例: $0 batch ch001-ch010"
    echo ""
    echo "  status                   查看当前阅读进度"
    echo ""
    echo "  report [章节范围]       生成读者评论汇总"
    echo "     示例: $0 report ch001-ch010"
    echo ""
    echo "==========================================="
}

# 解析章节范围
# 输入: ch001-ch010
# 输出: 章节编号数组
parse_chapter_range() {
    local range="$1"
    local start="${range%-*}"
    local end="${range#*-}"

    # 提取数字部分
    start_num=$(echo "$start" | sed 's/ch//')
    end_num=$(echo "$end" | sed 's/ch//')

    chapters=()
    for i in $(seq $start_num $end_num); do
        # 补零处理
        if [ $i -lt 10 ]; then
            chapters+=("ch00$i")
        elif [ $i -lt 100 ]; then
            chapters+=("ch0$i")
        else
            chapters+=("ch$i")
        fi
    done

    echo "${chapters[@]}"
}

# 验证读者是否存在
validate_reader() {
    local reader="$1"
    for r in "${READERS[@]}"; do
        if [ "$r" == "$reader" ]; then
            return 0
        fi
    done
    return 1
}

# 验证章节是否存在
validate_chapters() {
    local range="$1"
    local chapters=($(parse_chapter_range "$range"))

    for ch in "${chapters[@]}"; do
        if [ ! -f "$CONTENT_STORE/${ch}.md" ]; then
            log_error "章节文件不存在: ${ch}.md"
            return 1
        fi
    done
    return 0
}

# 创建输出目录
ensure_directories() {
    mkdir -p "$OPINIONS"
    mkdir -p "$READER_POOL/读者A/comments"
    mkdir -p "$READER_POOL/读者B/comments"
    mkdir -p "$READER_POOL/读者C/comments"
    mkdir -p "$READER_POOL/读者D/comments"
    mkdir -p "$READER_POOL/读者E/comments"
    mkdir -p "$READER_POOL/读者F/comments"
    mkdir -p "$READER_POOL/读者G/comments"
    mkdir -p "$READER_POOL/读者H/comments"
    mkdir -p "$READER_POOL/读者I/comments"
    mkdir -p "$READER_POOL/读者J/comments"
    mkdir -p "$READER_POOL/读者K/comments"
    mkdir -p "$READER_POOL/读者L/comments"
    mkdir -p "$READER_POOL/读者M/comments"
    mkdir -p "$READER_POOL/读者N/comments"
    mkdir -p "$READER_POOL/读者O/comments"
    mkdir -p "$READER_POOL/读者P/comments"
    mkdir -p "$READER_POOL/读者Q/comments"
    mkdir -p "$READER_POOL/读者R/comments"
    mkdir -p "$READER_POOL/读者S/comments"
    mkdir -p "$READER_POOL/读者T/comments"
}

# 分配阅读任务
cmd_assign() {
    local reader="$1"
    local range="$2"

    if [ -z "$reader" ] || [ -z "$range" ]; then
        log_error "参数不足"
        echo "用法: $0 assign <读者> <章节范围>"
        exit 1
    fi

    if ! validate_reader "$reader"; then
        log_error "读者不存在: $reader"
        echo "可用读者: ${READERS[*]}"
        exit 1
    fi

    if ! validate_chapters "$range"; then
        log_error "章节验证失败"
        exit 1
    fi

    ensure_directories

    log_info "分配阅读任务: $reader → $range"

    # 读取读者profile
    local profile="$READER_POOL/$reader/CLAUDE.md"

    # 生成任务描述
    local chapters=($(parse_chapter_range "$range"))
    local task_desc="阅读以下章节并输出评论: ${chapters[*]}"

    log_success "任务已分配"
    log_info "任务详情:"
    echo "  - 读者: $reader"
    echo "  - 章节: $range"
    echo "  - 任务文件: $profile"

    # 输出任务清单
    echo ""
    echo "待阅读章节:"
    for ch in "${chapters[@]}"; do
        echo "    - $ch.md"
    done

    echo ""
    log_info "请在Claude Code中启动读者Agent执行任务"
}

# 批量启动读者并行阅读
cmd_batch() {
    local range="$1"

    if [ -z "$range" ]; then
        log_error "参数不足"
        echo "用法: $0 batch <章节范围>"
        exit 1
    fi

    if ! validate_chapters "$range"; then
        log_error "章节验证失败"
        exit 1
    fi

    ensure_directories

    log_info "批量启动读者并行阅读: $range"

    local chapters=($(parse_chapter_range "$range"))
    local total_chapters=${#chapters[@]}
    local total_readers=${#READERS[@]}

    # 计算每个读者应读的章节数
    local chapters_per_reader=$(( (total_chapters + total_readers - 1) / total_readers ))

    echo ""
    echo "==========================================="
    echo "         批量阅读任务分配"
    echo "==========================================="
    echo "总章节数: $total_chapters"
    echo "读者数量: $total_readers"
    echo "每读者章节: ~$chapters_per_reader"
    echo ""

    # 分配任务
    local reader_idx=0
    local start_idx=0

    for (( i=0; i<total_chapters; i+=chapters_per_reader )); do
        local end_idx=$((i + chapters_per_reader - 1))
        if [ $end_idx -ge $total_chapters ]; then
            end_idx=$((total_chapters - 1))
        fi

        # 构建本读者的章节范围
        local reader_chapters=()
        for (( j=i; j<=end_idx; j++ )); do
            reader_chapters+=("${chapters[$j]}")
        done

        local reader="${READERS[$reader_idx]}"
        local task_range="${reader_chapters[0]#ch}-${reader_chapters[-1]#ch}"

        echo "[$reader] → ch${task_range}"

        ((reader_idx++))
    done

    echo ""
    log_success "任务分配完成"
    echo ""
    log_info "请使用以下命令启动并行阅读:"
    echo "  for reader in ${READERS[*]}; do"
    echo "    ./run_reader.sh assign \$reader chXXX-chYYY &"
    echo "  done"
    echo ""
    log_info "或直接通过Claude Code的Agent工具批量启动20个读者Subagent"
}

# 查看阅读进度
cmd_status() {
    echo ""
    echo "==========================================="
    echo "         读者阅读进度"
    echo "==========================================="
    echo ""

    local total_readers=${#READERS[@]}
    local active_count=0
    local completed_count=0

    for reader in "${READERS[@]}"; do
        local profile="$READER_POOL/$reader/CLAUDE.md"
        local comments_dir="$READER_POOL/$reader/comments"

        if [ -f "$profile" ]; then
            # 统计评论文件数量
            local comment_count=0
            if [ -d "$comments_dir" ]; then
                comment_count=$(ls -1 "$comments_dir" 2>/dev/null | wc -l)
            fi

            echo "[$reader] 评论数: $comment_count"

            if [ $comment_count -gt 0 ]; then
                ((completed_count++))
            else
                ((active_count++))
            fi
        else
            echo "[$reader] 未找到CLAUDE.md"
        fi
    done

    echo ""
    echo "---------------------------------------"
    echo "汇总: 总读者数=$total_readers, 活跃=$active_count, 已完成=$completed_count"
    echo "---------------------------------------"
    echo ""
}

# 生成读者评论汇总
cmd_report() {
    local range="$1"

    echo ""
    echo "==========================================="
    echo "         读者评论汇总"
    echo "==========================================="
    echo ""

    if [ -n "$range" ]; then
        log_info "生成范围: $range"
        local chapters=($(parse_chapter_range "$range"))

        for ch in "${chapters[@]}"; do
            echo "--- $ch ---"

            # 搜索各读者的评论
            for reader in "${READERS[@]}"; do
                local comment_file="$READER_POOL/$reader/comments/${ch}_评论.md"
                if [ -f "$comment_file" ]; then
                    echo "[$reader]"
                    head -20 "$comment_file"
                    echo ""
                fi
            done
        done
    else
        # 全量汇总
        log_info "生成全量评论汇总..."

        for reader in "${READERS[@]}"; do
            local comments_dir="$READER_POOL/$reader/comments"

            if [ -d "$comments_dir" ]; then
                local comment_count=$(ls -1 "$comments_dir" 2>/dev/null | wc -l)
                if [ $comment_count -gt 0 ]; then
                    echo "[$reader] 完成 $comment_count 篇评论"
                fi
            fi
        done
    fi

    echo ""
    log_success "汇总完成"
    echo ""
    log_info "详细评论请查看: $OPINIONS/"
}

# 主逻辑
case "$1" in
    assign)
        cmd_assign "$2" "$3"
        ;;
    batch)
        cmd_batch "$2"
        ;;
    status)
        cmd_status
        ;;
    report)
        cmd_report "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -n "$1" ]; then
            log_error "未知命令: $1"
        fi
        show_help
        exit 1
        ;;
esac