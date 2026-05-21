#!/bin/bash
#===============================================================================
# 汇总部门 · 执行脚本 v2.0
# 用法: ./run_summary.sh [command] [params]
#
# v2.0 新增: merge 命令支持分层合并
#   ./run_summary.sh merge stage 卷1_阶段1  # 合并阶段正文
#   ./run_summary.sh merge volume 卷1        # 合并卷正文
#   ./run_summary.sh merge full             # 合并全文正文
#===============================================================================

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)/.."
SUMMARY_DIR="$PROJECT_ROOT/07_汇总仓库"
CONTENT_DIR="$PROJECT_ROOT/03_内容仓库"
STAGE_SUMMARY_DIR="$SUMMARY_DIR/阶段正文"
PUBLISHED_DIR="$PROJECT_ROOT/08_已发布"

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

# 检查目录是否存在
function check_dirs() {
    if [ ! -d "$SUMMARY_DIR" ]; then
        log_error "汇总仓库不存在: $SUMMARY_DIR"
        exit 1
    fi
    if [ ! -d "$CONTENT_DIR" ]; then
        log_error "内容仓库不存在: $CONTENT_DIR"
        exit 1
    fi
}

# 显示帮助
function show_help() {
    echo "汇总部门执行脚本 v2.0"
    echo ""
    echo "用法: $0 [command] [params]"
    echo ""
    echo "命令:"
    echo "  init 卷N       - 初始化卷汇总任务"
    echo "  stage 阶段N   - 执行阶段汇总"
    echo "  volume 卷N    - 执行卷汇总"
    echo "  full          - 执行全文汇总"
    echo "  verify        - 验证汇总完整性"
    echo "  merge         - 合并正文（新增）"
    echo ""
    echo "合并命令:"
    echo "  merge stage 卷1_阶段1  - 合并阶段正文"
    echo "  merge volume 卷1      - 合并卷正文"
    echo "  merge full            - 合并全文正文"
    echo ""
    echo "示例:"
    echo "  $0 init 卷1          # 初始化卷1汇总任务"
    echo "  $0 stage 阶段1        # 执行阶段1汇总"
    echo "  $0 volume 卷1         # 执行卷1汇总"
    echo "  $0 full              # 执行全文汇总"
    echo "  $0 merge stage 卷1_阶段1  # 合并阶段1正文"
    echo "  $0 merge volume 卷1       # 合并卷1正文"
    echo "  $0 merge full            # 合并全文正文"
    echo "  $0 verify             # 验证汇总完整性"
}

# 列出已存在的汇总
function list_summaries() {
    echo "=== 已存在汇总 ==="
    echo ""
    echo "--- 阶段汇总 ---"
    ls "$STAGE_SUMMARY_DIR" 2>/dev/null | grep -E "阶段[0-9]+" | sort
    echo ""
    echo "--- 卷汇总 ---"
    ls "$SUMMARY_DIR"/*.md 2>/dev/null | grep -v "校验报告\|工作流程\|profile" | xargs -I{} basename {}
}

# ==================== 命令实现 ====================

# 1. init - 初始化卷汇总任务
function cmd_init() {
    local volume=$1
    if [ -z "$volume" ]; then
        log_error "用法: $0 init 卷N"
        exit 1
    fi

    log_info "初始化卷汇总任务: $volume"

    local volume_num=$(echo "$volume" | sed 's/卷//')
    local work_dir="$SUMMARY_DIR/工作区/$volume"

    mkdir -p "$work_dir"

    echo "=== $volume 汇总任务初始化 ==="
    echo ""
    echo "工作目录: $work_dir"
    echo ""
    echo "请按以下顺序执行："
    echo "  1. $0 stage 阶段1"
    echo "  2. $0 stage 阶段2"
    echo "  ..."
    echo "  6. $0 stage 阶段6"
    echo "  7. $0 volume $volume"
    echo ""
    echo "完成后执行: $0 verify"
}

# 2. stage - 执行阶段汇总
function cmd_stage() {
    local stage=$1
    if [ -z "$stage" ]; then
        log_error "用法: $0 stage 阶段N"
        exit 1
    fi

    log_info "执行阶段汇总: $stage"

    local stage_num=$(echo "$stage" | sed 's/阶段//')
    local output_file="$STAGE_SUMMARY_DIR/卷1_${stage}_汇总.md"

    echo ""
    echo "=== 执行 $stage 汇总 ==="
    echo ""

    # 查找该阶段的章节
    local stage_chapters=$(find "$CONTENT_DIR" -name "*.md" -type f | \
        xargs grep -l "## ${stage}" 2>/dev/null | head -20)

    if [ -z "$stage_chapters" ]; then
        log_warn "未找到 ${stage} 相关章节，尝试查找chxxx.md文件"

        # 估算章节范围（假设每阶段约10章）
        local start_ch=$(( (stage_num - 1) * 10 + 1))
        local end_ch=$(( stage_num * 10 ))

        echo "估算章节范围: ch$(printf '%03d' $start_ch) - ch$(printf '%03d' $end_ch)"
        echo ""
    fi

    echo "汇总主笔执行："
    echo "  1. 读取 ${stage} 内所有章节"
    echo "  2. 提取关键事件清单"
    echo "  3. 撰写过渡段落"
    echo "  4. 输出到: $output_file"
    echo ""
    echo "汇总编辑审核："
    echo "  1. 检查风格统一"
    echo "  2. 润色过渡段落"
    echo ""
    echo "汇总校验检查："
    echo "  1. 一致性验证"
    echo "  2. 时间线核查"
    echo ""
    echo "请在主会话中启动汇总部门Agent执行"
}

# 3. volume - 执行卷汇总
function cmd_volume() {
    local volume=$1
    if [ -z "$volume" ]; then
        log_error "用法: $0 volume 卷N"
        exit 1
    fi

    log_info "执行卷汇总: $volume"

    local volume_num=$(echo "$volume" | sed 's/卷//')
    local output_file="$SUMMARY_DIR/${volume}_汇总.md"

    echo ""
    echo "=== 执行 $volume 汇总 ==="
    echo ""

    # 列出该卷所有阶段汇总
    echo "该卷阶段汇总："
    ls "$STAGE_SUMMARY_DIR"/*${volume}* 2>/dev/null | xargs -I{} basename {} | sed 's/^/  /'
    echo ""

    echo "汇总主笔执行："
    echo "  1. 读取该卷所有阶段汇总"
    echo "  2. 整合为卷汇总"
    echo "  3. 撰写卷衔接段落"
    echo "  4. 输出到: $output_file"
    echo ""
    echo "汇总编辑审核："
    echo "  1. 检查卷内风格统一"
    echo "  2. 润色卷过渡"
    echo ""
    echo "汇总校验检查："
    echo "  1. 跨阶段一致性"
    echo "  2. 人物状态追踪"
    echo "  3. 输出 consistency_report_${volume}.md"
    echo ""

    if [ "$volume_num" -eq 1 ]; then
        echo "卷1汇总完成后，可执行: $0 full (执行全文汇总)"
    fi
}

# 4. full - 执行全文汇总
function cmd_full() {
    log_info "执行全文汇总"

    local output_file="$SUMMARY_DIR/全文汇总.md"

    echo ""
    echo "=== 执行全文汇总 ==="
    echo ""

    # 列出所有卷汇总
    echo "所有卷汇总："
    ls "$SUMMARY_DIR"/卷*_汇总.md 2>/dev/null | xargs -I{} basename {} | sed 's/^/  /'
    echo ""

    echo "汇总主笔执行："
    echo "  1. 读取所有卷汇总"
    echo "  2. 整合为全文汇总"
    echo "  3. 撰写卷间衔接"
    echo "  4. 输出到: $output_file"
    echo ""
    echo "汇总编辑审核："
    echo "  1. 全局风格统一"
    echo "  2. 全文语气一致"
    echo ""
    echo "汇总校验检查："
    echo "  1. 跨卷一致性"
    echo "  2. 全文时间线验证"
    echo "  3. 人物命运追踪"
    echo "  4. 输出 consistency_report_全文.md"
    echo ""
    echo "全文汇总定稿后，更新 workflow_state.json 进入 PHASE_7_RELEASE"
}

# 5. verify - 验证汇总完整性
function cmd_verify() {
    log_info "验证汇总完整性"

    echo ""
    echo "=== 汇总完整性验证 ==="
    echo ""

    local has_issues=0

    # 检查阶段正文（合并后的阶段正文文件）
    echo "--- 阶段正文检查 ---"
    local stage_count=$(ls "$STAGE_SUMMARY_DIR"/*正文*.md 2>/dev/null | wc -l)
    echo "阶段正文数量: $stage_count (预期: 17个阶段)"

    if [ "$stage_count" -lt 17 ]; then
        log_warn "阶段正文数量不足"
        has_issues=1
    fi

    # 检查卷正文
    echo ""
    echo "--- 卷正文检查 ---"
    local vol_count=$(ls "$SUMMARY_DIR/卷正文"/*.md 2>/dev/null | wc -l)
    echo "卷正文数量: $vol_count (预期: 3卷)"

    if [ "$vol_count" -lt 3 ]; then
        log_warn "卷正文数量不足"
        has_issues=1
    fi

    # 检查全文正文
    echo ""
    echo "--- 全文正文检查 ---"
    if ls "$SUMMARY_DIR/全文正文"/*.md 2>/dev/null | grep -q .; then
        local full_count=$(ls "$SUMMARY_DIR/全文正文"/*.md 2>/dev/null | wc -l)
        log_info "全文正文已生成 ($full_count 个版本)"
        echo "最新文件:"
        ls -lh "$SUMMARY_DIR/全文正文"/*.md 2>/dev/null | tail -1 | awk '{print "  "$9" ("5")"}'
    else
        log_warn "全文正文未生成"
        has_issues=1
    fi

    # 检查汇总报告（可选，作为参考）
    echo ""
    echo "--- 汇总报告检查 ---"
    local report_count=$(ls "$SUMMARY_DIR/汇总报告"/*汇总*.md 2>/dev/null | wc -l)
    echo "汇总报告数量: $report_count (参考值)"

    # 汇总完整性判定
    echo ""
    echo "=== 验证结果 ==="
    if [ $has_issues -eq 0 ] && [ "$vol_count" -ge 3 ] && [ -d "$SUMMARY_DIR/全文正文" ]; then
        log_info "汇总完整性验证通过"
        echo ""
        echo "下一步: 更新 workflow_state.json 进入 PHASE_7_RELEASE"
    else
        log_warn "汇总不完整，请先完成缺失部分"
        echo ""
        echo "缺失部分需执行:"
        echo "  - 阶段正文: $0 merge stage <阶段名>"
        echo "  - 卷正文: $0 merge volume <卷名>"
        echo "  - 全文正文: $0 merge full"
    fi
}

# ==================== v2.0 新增：合并命令 ====================

# 获取项目名
function get_project_name() {
    if [[ -f "workflow_state.json" ]]; then
        grep -o '"project_name"[[:space:]]*:[[:space:]]*"[^"]*"' workflow_state.json | cut -d'"' -f4
    fi
    echo "星陨纪元"
}

# 阶段章节范围映射
function get_stage_chapters() {
    local stage_name="$1"
    # 根据章节大纲估算章节范围（每阶段约20章）
    case "$stage_name" in
        卷1_阶段1) echo "1-20" ;;
        卷1_阶段2) echo "21-40" ;;
        卷1_阶段3) echo "41-60" ;;
        卷1_阶段4) echo "61-80" ;;
        卷1_阶段5) echo "81-100" ;;
        卷1_阶段6) echo "101-120" ;;
        卷1_阶段7) echo "121-140" ;;
        卷2_阶段1) echo "141-160" ;;
        卷2_阶段2) echo "161-180" ;;
        卷2_阶段3) echo "181-200" ;;
        卷2_阶段4) echo "201-220" ;;
        卷2_阶段5) echo "221-240" ;;
        卷3_阶段1) echo "241-260" ;;
        卷3_阶段2) echo "261-280" ;;
        卷3_阶段3) echo "281-300" ;;
        卷3_阶段4) echo "301-320" ;;
        卷3_阶段5) echo "321-360" ;;
        *) echo "" ;;
    esac
}

# 卷章节范围映射
function get_volume_chapters() {
    local volume="$1"
    case "$volume" in
        卷1) echo "1-140" ;;
        卷2) echo "141-240" ;;
        卷3) echo "241-360" ;;
        *) echo "" ;;
    esac
}

# 合并正文函数
function cmd_merge() {
    local merge_type="$1"  # stage/volume/full
    local merge_target="$2"  # 卷1_阶段1 / 卷1 / 空

    echo -e "${BLUE}=== 合并正文 ===${NC}"
    echo ""

    local project_name=$(get_project_name)
    local version="v1.0"
    local output_dir="$PUBLISHED_DIR"
    local range_start=""
    local range_end=""

    if [[ "$merge_type" == "stage" ]]; then
        # 阶段合并
        if [[ -z "$merge_target" ]]; then
            log_error "请指定阶段: $0 merge stage 卷1_阶段1"
            exit 1
        fi
        local range=$(get_stage_chapters "$merge_target")
        if [[ -z "$range" ]]; then
            log_error "未知阶段: $merge_target"
            exit 1
        fi
        range_start=${range%-*}
        range_end=${range#*-}
        local output_dir="$SUMMARY_DIR/阶段正文"
        local output_file="${output_dir}/${project_name}_${merge_target}_正文_${version}.md"
        echo -e "${YELLOW}[1/4] 合并类型: 阶段正文${NC}"
        echo -e "${YELLOW}[2/4] 阶段: $merge_target${NC}"
        echo -e "${YELLOW}[3/4] 章节范围: ch${range_start}-ch${range_end}${NC}"
        echo -e "${YELLOW}[4/4] 输出文件: $output_file${NC}"

    elif [[ "$merge_type" == "volume" ]]; then
        # 卷合并
        if [[ -z "$merge_target" ]]; then
            log_error "请指定卷: $0 merge volume 卷1"
            exit 1
        fi
        local range=$(get_volume_chapters "$merge_target")
        if [[ -z "$range" ]]; then
            log_error "未知卷: $merge_target"
            exit 1
        fi
        range_start=${range%-*}
        range_end=${range#*-}
        local output_dir="$SUMMARY_DIR/卷正文"
        local output_file="${output_dir}/${project_name}_${merge_target}_正文_${version}.md"
        echo -e "${YELLOW}[1/4] 合并类型: 卷正文${NC}"
        echo -e "${YELLOW}[2/4] 卷: $merge_target${NC}"
        echo -e "${YELLOW}[3/4] 章节范围: ch${range_start}-ch${range_end}${NC}"
        echo -e "${YELLOW}[4/4] 输出文件: $output_file${NC}"

    elif [[ "$merge_type" == "full" ]]; then
        # 全文合并
        range_start=1
        range_end=360
        local output_dir="$SUMMARY_DIR/全文正文"
        local output_file="${output_dir}/${project_name}_全文正文_${version}.md"
        echo -e "${YELLOW}[1/4] 合并类型: 全文正文${NC}"
        echo -e "${YELLOW}[2/4] 章节范围: ch${range_start}-ch${range_end}${NC}"
        echo -e "${YELLOW}[3/4] 输出文件: $output_file${NC}"
        echo -e "${YELLOW}[4/4] 合并中...${NC}"
    else
        log_error "未知合并类型: $merge_type"
        echo "用法:"
        echo "  $0 merge stage 卷1_阶段1  # 合并阶段正文"
        echo "  $0 merge volume 卷1       # 合并卷正文"
        echo "  $0 merge full             # 合并全文正文"
        exit 1
    fi

    # 执行合并
    mkdir -p "$output_dir"
    > "$output_file"

    local chapter_dir="03_内容仓库/04_正文"
    local merged=0

    for i in $(seq $range_start $range_end); do
        local fname=$(printf "ch%03d.md" $i)
        local fpath="$chapter_dir/$fname"

        if [[ -f "$fpath" ]]; then
            echo -e "\n\n---\n\n# 第${i}章\n\n" >> "$output_file"
            cat "$fpath" >> "$output_file"
            merged=$((merged + 1))
            if [[ $((merged % 20)) -eq 0 ]]; then
                echo -e "  已合并: $merged / $((range_end - range_start + 1))"
            fi
        else
            echo -e "${YELLOW}  ⚠ 缺失: $fname${NC}"
        fi
    done

    local lines=$(wc -l < "$output_file")
    local size=$(du -h "$output_file" | cut -f1)

    echo ""
    echo -e "${GREEN}=== 合并完成 ===${NC}"
    echo "输出文件: $output_file"
    echo "合并章节: $merged 个"
    echo "总行数: $lines"
    echo "文件大小: $size"
}

# ==================== 主入口 ====================

check_dirs

case "$1" in
    init)       cmd_init "$2" ;;
    stage)      cmd_stage "$2" ;;
    volume)     cmd_volume "$2" ;;
    full)       cmd_full ;;
    verify)     cmd_verify ;;
    merge)      cmd_merge "$2" "$3" ;;
    list)       list_summaries ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -z "$1" ]; then
            show_help
            list_summaries
        else
            log_error "未知命令: $1"
            show_help
            exit 1
        fi
        ;;
esac