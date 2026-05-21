#!/bin/bash
# 小说工作室 · 工作流编排脚本 v1.3
# 用法: ./run_workflow.sh [command] [params]

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"

# 检查jq是否可用
JQ_AVAILABLE=false
if command -v jq > /dev/null 2>&1; then
    JQ_AVAILABLE=true
fi

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

function log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
function log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
function log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

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
        # Python fallback - write script to temp file
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

# 条件执行jq（仅当可用时）
function jq_run() {
    if [ "$JQ_AVAILABLE" = true ]; then
        "$@" 2>/dev/null
        return 0
    fi
    return 1
}

# ==================== 命令实现 ====================

function cmd_init() {
    log_info "初始化小说工作室工作流..."
    if [ -f "$WORKFLOW_FILE" ]; then
        log_error "工作流已存在，不重复初始化"
        exit 1
    fi
    cat > "$WORKFLOW_FILE" << 'EOF'
{
  "version": "1.3",
  "current_phase": "PHASE_0_SETUP",
  "current_step": "SETUP_00",
  "initialized_at": "2026-05-14",
  "agent_tasks": {},
  "project_info": {},
  "review_queue": { "pending": [], "in_review": [], "completed": [] },
  "phases": {},
  "deadline_check": {},
  "next_actions": []
}
EOF
    log_info "工作流初始化完成，状态: PHASE_0_SETUP"
}

function cmd_status() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在，请先运行 init"
        exit 1
    fi
    echo "=== 当前状态 ==="
    echo "版本: $(jq_get '.version' 'N/A')"
    echo "阶段: $(jq_get '.current_phase' 'N/A')"
    echo "步骤: $(jq_get '.current_step' 'N/A')"
    echo ""

    local task_count=$(jq_get '.agent_tasks | length' '0')
    echo "=== Agent任务 ($task_count) ==="
    if [ "$task_count" -gt 0 ] && [ "$JQ_AVAILABLE" = true ]; then
        jq -r '.agent_tasks | to_entries[] | "  \(.key): \(.value.status) (\(.value.agent))"' "$WORKFLOW_FILE" 2>/dev/null
    else
        echo "  (无进行中任务)"
    fi
    echo ""

    local next=$(jq_get '.next_actions[0]' '')
    if [ -n "$next" ]; then
        echo "下一步: $next"
    fi
}

function cmd_advance() {
    local target_step=$1
    if [ -z "$target_step" ]; then
        log_error "用法: ./run_workflow.sh advance STEP_03"
        exit 1
    fi
    log_info "推进到步骤: $target_step"
    log_warn "注意: 状态更新需由主会话人工执行（遵守反馈循环规则）"

    if [ "$JQ_AVAILABLE" = true ]; then
        jq --arg step "$target_step" '.current_step = $step' "$WORKFLOW_FILE" > tmp_$$.json && mv tmp_$$.json "$WORKFLOW_FILE"
    else
        log_warn "jq不可用，无法自动更新文件，请手动编辑workflow_state.json"
    fi
}

function cmd_launch() {
    local task_name=$1
    local agent=$2
    local task_desc=${3:-""}

    if [ -z "$task_name" ] || [ -z "$agent" ]; then
        log_error "用法: ./run_workflow.sh launch <task_name> <agent> [task_desc]"
        exit 1
    fi

    log_info "启动Agent: [$agent] -> $task_name"
    echo "任务描述: $task_desc"
    echo ""
    echo "请在主会话中使用 Agent 工具启动，并记录返回的 task_id"
    echo "然后运行: ./run_workflow.sh verify <task_name> <task_id>"
    echo ""

    if [ "$JQ_AVAILABLE" = true ]; then
        local timestamp=$(date +%Y-%m-%dT%H:%M:%S)
        jq --arg name "$task_name" \
           --arg agent "$agent" \
           --arg status "pending" \
           --arg dispatched "$timestamp" \
           '.agent_tasks[$name] = {"agent": $agent, "status": $status, "dispatched_at": $dispatched, "task_id": null}' \
           "$WORKFLOW_FILE" > tmp_$$.json && mv tmp_$$.json "$WORKFLOW_FILE"
        log_info "已创建任务记录到agent_tasks"
    else
        log_warn "jq不可用，请在主会话中手动记录task_id到workflow_state.json"
    fi
}

function cmd_verify() {
    local task_name=$1
    local task_id=$2

    if [ -z "$task_name" ] || [ -z "$task_id" ]; then
        log_error "用法: ./run_workflow.sh verify <task_name> <task_id>"
        exit 1
    fi

    log_info "验证任务: $task_name (task_id: $task_id)"
    echo ""
    echo "请在主会话中执行: TaskOutput(block=true, task_id=\"$task_id\", timeout=60000)"
    echo ""
    echo "验证通过后，更新workflow_state.json中agent_tasks的状态为'verified'"
}

function cmd_assign_batch() {
    local type=$1
    local range=$2

    if [ -z "$type" ] || [ -z "$range" ]; then
        log_error "用法: ./run_workflow.sh assign_batch <type> <range>"
        log_error "  type: writer/reviewer"
        log_error "  range: ch001-ch010 或 卷1"
        exit 1
    fi

    log_info "批量分配: $type -> $range"
    echo ""

    if [ "$type" == "writer" ]; then
        echo "10作家并行修改（每人一章）："
        echo "  作家A → 第1章"
        echo "  作家B → 第2章"
        echo "  ..."
        echo "  作家J → 第10章"
        echo ""
        echo "请在主会话中启动10个作家Agent并行执行"
        echo "每个Agent完成后验证并记录到agent_tasks"
    elif [ "$type" == "reviewer" ]; then
        echo "5审核员并行审核（每2人审一批）："
        echo "  审核员A+审核员B → 审第1-5章"
        echo "  审核员C+审核员D → 审第6-10章"
        echo "  审核员E → 备用+终审"
        echo ""
        echo "请在主会话中启动审核员Agent并行执行"
    else
        log_error "未知的type: $type"
    fi
}

function cmd_assign_reviewer() {
    local reviewer=$1
    local range=$2

    if [ -z "$reviewer" ] || [ -z "$range" ]; then
        log_error "用法: ./run_workflow.sh assign_reviewer <reviewer> <range>"
        exit 1
    fi

    log_info "分配审核员: [$reviewer] -> 审核 $range"
    echo "请在主会话中启动审核员Agent执行审核任务"
}

function cmd_assign_汇总员() {
    local role=$1
    local task=$2

    if [ -z "$role" ] || [ -z "$task" ]; then
        log_error "用法: ./run_workflow.sh assign_汇总员 <role> <task>"
        log_error "  role: 汇总主笔/汇总编辑/汇总校验"
        exit 1
    fi

    log_info "调度汇总部门: [$role] -> $task"
    echo ""
    echo "汇总部门执行修复时必须："
    echo "  1. 读取问题文件"
    echo "  2. 执行指定修复"
    echo "  3. 输出修复报告"
    echo "  4. 主控验证后标记verified"
    echo ""
    echo "禁止：直接修改文件而不通过Agent"
}

function cmd_assign() {
    local agent=$1
    local task=$2
    if [ -z "$agent" ] || [ -z "$task" ]; then
        log_error "用法: ./run_workflow.sh assign <agent> <task>"
        exit 1
    fi
    log_info "分配任务: [$agent] -> $task"
}

function cmd_report() {
    echo "=== 小说工作室状态报告 ==="
    echo "项目路径: $PROJECT_ROOT"
    echo "状态文件: $WORKFLOW_FILE"
    echo ""
    if [ -f "$WORKFLOW_FILE" ]; then
        echo "当前阶段: $(jq_get '.current_phase' 'N/A')"
        echo "当前步骤: $(jq_get '.current_step' 'N/A')"
        echo "版本: $(jq_get '.version' 'N/A')"
        echo ""

        echo "=== Agent 统计 ==="
        echo "灵感部门: $(jq_get '.agents.灵感部门.count' '3') 人"
        echo "作家部门: $(jq_get '.agents.作家部门.count' '10') 人"
        echo "审核部门: $(jq_get '.agents.审核部门.count' '10') 人"
        echo "读者部门: $(jq_get '.agents.读者部门.count' '20') 人"
        echo "汇总部门: $(jq_get '.agents.汇总部门.count' '3') 人"
        echo ""

        echo "=== 进行中任务 ==="
        local running=""
        if [ "$JQ_AVAILABLE" = true ]; then
            running=$(jq -r '.agent_tasks | to_entries[] | select(.value.status=="running") | "\(.key): \(.value.agent)"' "$WORKFLOW_FILE" 2>/dev/null)
        fi
        if [ -z "$running" ]; then
            echo "（无进行中任务）"
        else
            echo "$running"
        fi
    fi
}

function cmd_phases() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi
    echo "=== 所有阶段 ==="
    if [ "$JQ_AVAILABLE" = true ]; then
        jq -r '.phases | to_entries[] | "\(.key): \(.value.name) - \(.value.status)"' "$WORKFLOW_FILE" 2>/dev/null
    else
        echo "（jq不可用，请查看workflow_state.json）"
    fi
}

function cmd_tasks() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi
    echo "=== Agent任务追踪 ==="
    local count=$(jq_get '.agent_tasks | length' '0')
    echo "总任务数: $count"
    echo ""

    if [ "$count" -gt 0 ] && [ "$JQ_AVAILABLE" = true ]; then
        jq -r '.agent_tasks | to_entries[] |
            "任务: \(.key)
             Agent: \(.value.agent)
             状态: \(.value.status)
             TaskID: \(.value.task_id // "null")
             启动: \(.value.dispatched_at // "N/A")
             验证: \(.value.verified_at // "N/A")
             ---"' "$WORKFLOW_FILE" 2>/dev/null
    else
        echo "（无任务记录，或jq不可用）"
    fi
}

function cmd_next() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi
    echo "=== 下一步操作建议 ==="
    local phase=$(jq_get '.current_phase' 'N/A')
    local step=$(jq_get '.current_step' 'N/A')
    echo "当前: $phase / $step"
    echo ""

    if [ "$JQ_AVAILABLE" = true ]; then
        jq -r '.next_actions[]' "$WORKFLOW_FILE" 2>/dev/null | while read action; do
            echo "  → $action"
        done
    else
        echo "（jq不可用，请在workflow_state.json中查看next_actions）"
    fi
}

function cmd_block() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi
    echo "=== 当前阻塞点分析 ==="

    local phase=$(jq_get '.current_phase' 'N/A')
    local step=$(jq_get '.current_step' 'N/A')

    if [ "$JQ_AVAILABLE" = true ]; then
        # 检查阻塞条件
        local pending_count=$(jq -r '.review_queue.pending | length' "$WORKFLOW_FILE" 2>/dev/null || echo 0)
        local in_review_count=$(jq -r '.review_queue.in_review | length' "$WORKFLOW_FILE" 2>/dev/null || echo 0)

        echo "当前阶段: $phase"
        echo "当前步骤: $step"
        echo ""
        echo "审核队列:"
        echo "  待处理: $pending_count"
        echo "  审核中: $in_review_count"
        echo ""

        # 检测可能的阻塞
        if [ "$pending_count" -gt 10 ]; then
            echo "⚠️  警告: 待处理审核超过10个，可能导致流程阻塞"
        fi

        # 检查pending的任务
        local running_tasks=$(jq -r '.agent_tasks | to_entries[] | select(.value.status=="running") | .key' "$WORKFLOW_FILE" 2>/dev/null | wc -l)
        if [ "$running_tasks" -gt 5 ]; then
            echo "⚠️  警告: 运行中任务超过5个，可能需要等待完成"
        fi

        echo ""
        echo "如需解决阻塞，请执行："
        echo "  ./run_workflow.sh review_status    # 查看审核队列"
        echo "  ./run_workflow.sh tasks            # 查看进行中任务"
    else
        echo "jq不可用，请手动检查workflow_state.json"
    fi
}

function cmd_agent_list() {
    echo "=== 可用Agent列表 ==="
    echo ""
    echo "灵感部门 (3人):"
    echo "  灵感A - 类型专家（都市/职场）"
    echo "  灵感B - 幻想专家（玄幻/科幻）"
    echo "  灵感C - 结构专家（悬疑/叙事）"
    echo ""
    echo "作家部门 (10人):"
    echo "  作家A ~ 作家J"
    echo "  每位作家擅长不同类型，可并行修改"
    echo ""
    echo "审核部门 (10人):"
    echo "  审核员A - 逻辑严密度"
    echo "  审核员B - 人设稳定性"
    echo "  审核员C - 叙事节奏"
    echo "  审核员D - 市场适配"
    echo "  审核员E - 设定冲突检测"
    echo "  审核员F ~ J - 其他专项"
    echo ""
    echo "读者部门 (20人):"
    echo "  读者A ~ 读者T"
    echo "  批量阅读，并行评论"
    echo ""
    echo "汇总部门 (3人):"
    echo "  汇总主笔 - 整合写作"
    echo "  汇总编辑 - 润色统一"
    echo "  汇总校验 - 一致性核查"
}

function cmd_review_status() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi
    echo "=== 审核队列状态 ==="

    if [ "$JQ_AVAILABLE" = true ]; then
        echo "待处理:"
        jq -r '.review_queue.pending[]' "$WORKFLOW_FILE" 2>/dev/null | while read batch; do
            echo "  ○ $batch"
        done

        echo ""
        echo "审核中:"
        jq -r '.review_queue.in_review[]' "$WORKFLOW_FILE" 2>/dev/null | while read batch; do
            echo "  ◐ $batch"
        done

        echo ""
        echo "已完成: $(jq -r '.review_queue.completed | length' "$WORKFLOW_FILE" 2>/dev/null) 批次"
        jq -r '.review_queue.completed[-5:][]' "$WORKFLOW_FILE" 2>/dev/null | while read batch; do
            echo "  ✓ $batch"
        done
    else
        echo "jq不可用，请查看workflow_state.json中的review_queue字段"
    fi
}

function cmd_summary_status() {
    echo "=== 汇总进度状态 ==="

    if [ "$JQ_AVAILABLE" = true ]; then
        # 阶段汇总
        if [ -d "$PROJECT_ROOT/07_汇总仓库/阶段汇总" ]; then
            local stage_count=$(find "$PROJECT_ROOT/07_汇总仓库/阶段汇总" -name "*.md" 2>/dev/null | wc -l)
            echo "阶段汇总: $stage_count 个"
        else
            echo "阶段汇总: (目录不存在)"
        fi

        # 卷汇总
        if [ -d "$PROJECT_ROOT/03_内容仓库/02_卷大纲" ]; then
            local volume_count=$(find "$PROJECT_ROOT/03_内容仓库/02_卷大纲" -maxdepth 1 -type d | tail -n +2 | wc -l)
            echo "卷大纲: $volume_count 卷"
        else
            echo "卷大纲: (目录不存在)"
        fi

        # 全文汇总
        if [ -f "$PROJECT_ROOT/07_汇总仓库/汇总主笔/全文汇总_星陨纪元.md" ]; then
            echo "全文汇总: ✓ 已生成"
        else
            echo "全文汇总: ✗ 未生成"
        fi
    else
        echo "jq不可用，请手动检查"
    fi
}

function cmd_issues() {
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "工作流文件不存在"
        exit 1
    fi
    echo "=== 已发现问题汇总 ==="

    if [ "$JQ_AVAILABLE" = true ]; then
        local issue_count=$(jq -r '.issues_found | length' "$WORKFLOW_FILE" 2>/dev/null || echo 0)
        echo "问题批次: $issue_count"
        echo ""

        jq -r '.issues_found | to_entries[] |
            "\(.key):
             \(.value | length) 条问题"' "$WORKFLOW_FILE" 2>/dev/null | head -20
    else
        echo "jq不可用，请查看workflow_state.json中的issues_found字段"
    fi
}

# ==================== 主入口 ====================

case "$1" in
    init)            cmd_init ;;
    status)          cmd_status ;;
    advance)         cmd_advance "$2" ;;
    launch)          cmd_launch "$2" "$3" "$4" ;;
    verify)          cmd_verify "$2" "$3" ;;
    assign_batch)    cmd_assign_batch "$2" "$3" ;;
    assign_reviewer) cmd_assign_reviewer "$2" "$3" ;;
    assign_汇总员)   cmd_assign_汇总员 "$2" "$3" ;;
    assign)          cmd_assign "$2" "$3" ;;
    report)          cmd_report ;;
    phases)          cmd_phases ;;
    tasks)           cmd_tasks ;;
    next)            cmd_next ;;
    block)           cmd_block ;;
    agent_list)      cmd_agent_list ;;
    review_status)   cmd_review_status ;;
    summary_status)  cmd_summary_status ;;
    issues)          cmd_issues ;;
    *)
        echo "用法: $0 {init|status|advance|launch|verify|assign|assign_batch|assign_reviewer|assign_汇总员|report|phases|tasks|next|block|agent_list|review_status|summary_status|issues}"
        echo ""
        echo "Commands:"
        echo "  init            - 初始化工作流（仅首次）"
        echo "  status          - 查看当前状态"
        echo "  advance         - 推进到指定步骤"
        echo "  launch          - 启动Agent并记录task_id"
        echo "  verify          - TaskOutput验证Agent完成状态"
        echo "  assign          - 分配任务给Agent（单任务）"
        echo "  assign_batch    - 批量并行分配（10章→10作家）"
        echo "  assign_reviewer - 分配审核员"
        echo "  assign_汇总员   - 调度汇总部门"
        echo "  report          - 生成状态报告"
        echo "  phases          - 列出所有阶段"
        echo "  tasks           - 查看当前agent_tasks"
        echo "  next            - 下一步操作建议"
        echo "  block           - 阻塞点分析"
        echo "  agent_list      - 可用Agent列表"
        echo "  review_status   - 审核队列状态"
        echo "  summary_status  - 汇总进度状态"
        echo "  issues          - 已发现问题汇总"
        exit 1
        ;;
esac