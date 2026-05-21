#!/bin/bash
#===============================================================================
# 灵文 · 新项目初始化脚本
# 用法: ./run_init.sh <项目名> <章节数> [卷数]
# 示例: ./run_init.sh 星陨纪元 360 3
#       ./run_init.sh 新书名 100 2
#===============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

#-------------------------------------------------------------------------------
# 帮助信息
#-------------------------------------------------------------------------------
show_help() {
    cat << EOF
${GREEN}灵文 · 新项目初始化脚本${NC}

${YELLOW}用法:${NC}
    ./run_init.sh <项目名> <章节数> [卷数]

${YELLOW}参数:${NC}
    项目名     - 小说名称（如：星陨纪元）
    章节数     - 总章节数（如：360）
    卷数       - 卷数，默认为3（如：3）

${YELLOW}示例:${NC}
    ./run_init.sh 星陨纪元 360 3
    ./run_init.sh 新书名 100 2

${YELLOW}功能:${NC}
    1. 创建项目文件夹结构
    2. 初始化 workflow_state.json
    3. 生成各层 index.json
    4. 更新主控记忆

EOF
}

#-------------------------------------------------------------------------------
# 检查参数
#-------------------------------------------------------------------------------
check_args() {
    if [ $# -lt 2 ]; then
        echo -e "${RED}错误: 参数不足${NC}"
        echo "用法: ./run_init.sh <项目名> <章节数> [卷数]"
        echo "示例: ./run_init.sh 星陨纪元 360 3"
        exit 1
    fi

    PROJECT_NAME="$1"
    CHAPTER_COUNT="$2"
    VOLUME_COUNT="${3:-3}"

    # 验证章节数为数字
    if ! [[ "$CHAPTER_COUNT" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}错误: 章节数必须是数字${NC}"
        exit 1
    fi

    # 验证卷数为数字
    if ! [[ "$VOLUME_COUNT" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}错误: 卷数必须是数字${NC}"
        exit 1
    fi

    echo -e "${BLUE}项目信息:${NC}"
    echo "  项目名称: $PROJECT_NAME"
    echo "  章节数: $CHAPTER_COUNT"
    echo "  卷数: $VOLUME_COUNT"
    echo ""
}

#-------------------------------------------------------------------------------
# 创建目录结构
#-------------------------------------------------------------------------------
create_dirs() {
    echo -e "${YELLOW}[1/4] 创建目录结构...${NC}"

    # 项目文件夹
    mkdir -p "$PROJECT_ROOT/01_灵感库/$PROJECT_NAME"
    mkdir -p "$PROJECT_ROOT/01_灵感库/$PROJECT_NAME/立项"

    # 各卷文件夹
    for i in $(seq 1 $VOLUME_COUNT); do
        mkdir -p "$PROJECT_ROOT/03_内容仓库/02_卷大纲/卷$i"
        mkdir -p "$PROJECT_ROOT/03_内容仓库/03_阶段大纲/卷$i"
        mkdir -p "$PROJECT_ROOT/03_内容仓库/04_正文/卷$i"
    done

    mkdir -p "$PROJECT_ROOT/06_意见仓库/01_全文大纲_审核"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/02_卷大纲_审核"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/03_阶段大纲_审核"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/04_正文_审核"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/05_作家修改"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/05_读者评论"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/06_汇总_审核"
    mkdir -p "$PROJECT_ROOT/06_意见仓库/情感审核"

    mkdir -p "$PROJECT_ROOT/07_汇总仓库/汇总主笔"
    mkdir -p "$PROJECT_ROOT/07_汇总仓库/汇总编辑"
    mkdir -p "$PROJECT_ROOT/07_汇总仓库/汇总校验"

    mkdir -p "$PROJECT_ROOT/08_已发布"

    echo -e "${GREEN}  目录结构创建完成${NC}"
}

#-------------------------------------------------------------------------------
# 初始化 workflow_state.json
#-------------------------------------------------------------------------------
init_workflow_state() {
    echo -e "${YELLOW}[2/4] 初始化 workflow_state.json...${NC}"

    if [ -f "$WORKFLOW_FILE" ]; then
        echo -e "${YELLOW}  备份现有 workflow_state.json → workflow_state.json.bak${NC}"
        cp "$WORKFLOW_FILE" "$WORKFLOW_FILE.bak"
    fi

    # 生成 chapters 数组
    chapters_json=""
    for i in $(seq 1 $CHAPTER_COUNT); do
        ch_num=$(printf "%03d" $i)
        chapters_json="$chapters_json\"ch$ch_num\", "
    done
    chapters_json="${chapters_json%, }"

    cat > "$WORKFLOW_FILE" << EOF
{
    "version": "1.3",
    "project_info": {
        "project_name": "$PROJECT_NAME",
        "total_chapters": $CHAPTER_COUNT,
        "volume_count": $VOLUME_COUNT,
        "chapters_per_volume": $(($CHAPTER_COUNT / $VOLUME_COUNT)),
        "created_at": "$(date +%Y-%m-%d)",
        "framework_version": "v1.3"
    },
    "current_phase": "PHASE_1_LAUNCH",
    "current_step": "STEP_01",
    "phases": {
        "PHASE_0_SETUP": {
            "status": "completed",
            "steps": {
                "SETUP_00": {"status": "completed", "name": "初始化"}
            }
        },
        "PHASE_1_LAUNCH": {
            "status": "pending",
            "steps": {
                "STEP_01": {"status": "pending", "name": "灵感生成"},
                "STEP_02": {"status": "pending", "name": "全文大纲初稿"}
            }
        },
        "PHASE_2_OUTLINE": {
            "status": "pending",
            "steps": {
                "STEP_03": {"status": "pending", "name": "全文大纲审核"},
                "STEP_04": {"status": "pending", "name": "全文大纲修改"},
                "STEP_05": {"status": "pending", "name": "全文大纲终审"}
            }
        },
        "PHASE_3_VOLUME": {
            "status": "pending",
            "steps": {
                "STEP_06": {"status": "pending", "name": "卷大纲生成"},
                "STEP_07": {"status": "pending", "name": "卷大纲审核"},
                "STEP_08": {"status": "pending", "name": "卷大纲修改"},
                "STEP_09": {"status": "pending", "name": "卷大纲终审"}
            }
        },
        "PHASE_4_STAGE": {
            "status": "pending",
            "steps": {
                "STEP_10": {"status": "pending", "name": "阶段大纲生成"},
                "STEP_11": {"status": "pending", "name": "阶段大纲审核"},
                "STEP_12": {"status": "pending", "name": "阶段大纲修改"},
                "STEP_13": {"status": "pending", "name": "阶段大纲终审"}
            }
        },
        "PHASE_5_BODY": {
            "status": "pending",
            "steps": {
                "STEP_14": {"status": "pending", "name": "正文创作"},
                "STEP_15": {"status": "pending", "name": "读者评论"},
                "STEP_16": {"status": "pending", "name": "正文审核"},
                "STEP_17": {"status": "pending", "name": "正文修改"},
                "STEP_18": {"status": "pending", "name": "正文定稿"}
            }
        },
        "PHASE_6_SUMMARY": {
            "status": "pending",
            "steps": {
                "STEP_19": {"status": "pending", "name": "阶段汇总"},
                "STEP_20": {"status": "pending", "name": "阶段汇总审核"},
                "STEP_21": {"status": "pending", "name": "阶段汇总微调"},
                "STEP_22": {"status": "pending", "name": "卷汇总"},
                "STEP_23": {"status": "pending", "name": "全文汇总"},
                "STEP_24": {"status": "pending", "name": "终审与发布"}
            }
        },
        "PHASE_7_CLOSE": {
            "status": "pending",
            "steps": {
                "STEP_25": {"status": "pending", "name": "归档与发布"}
            }
        }
    },
    "chapters": [$chapters_json],
    "agent_tasks": {},
    "issues": [],
    "next_actions": "准备启动 PHASE_1_LAUNCH → STEP_01 灵感生成"
}
EOF

    echo -e "${GREEN}  workflow_state.json 初始化完成${NC}"
}

#-------------------------------------------------------------------------------
# 生成各层 index.json
#-------------------------------------------------------------------------------
generate_indexes() {
    echo -e "${YELLOW}[3/4] 生成各层 index.json...${NC}"

    # 全文总体大纲 index
    cat > "$PROJECT_ROOT/03_内容仓库/01_全文总体大纲/index.json" << EOF
{
    "layer": "全文总体大纲",
    "project": "$PROJECT_NAME",
    "created_at": "$(date +%Y-%m-%d)",
    "entries": []
}
EOF

    # 卷大纲 index
    for i in $(seq 1 $VOLUME_COUNT); do
        cat > "$PROJECT_ROOT/03_内容仓库/02_卷大纲/卷$i/index.json" << EOF
{
    "layer": "卷大纲",
    "project": "$PROJECT_NAME",
    "volume": $i,
    "created_at": "$(date +%Y-%m-%d)",
    "entries": []
}
EOF
    done

    # 阶段大纲 index（按卷）
    for i in $(seq 1 $VOLUME_COUNT); do
        cat > "$PROJECT_ROOT/03_内容仓库/03_阶段大纲/卷$i/index.json" << EOF
{
    "layer": "阶段大纲",
    "project": "$PROJECT_NAME",
    "volume": $i,
    "created_at": "$(date +%Y-%m-%d)",
    "entries": []
}
EOF
    done

    # 正文 index（按卷）
    chapters_per_vol=$(($CHAPTER_COUNT / $VOLUME_COUNT))
    for i in $(seq 1 $VOLUME_COUNT); do
        # 生成该卷的章节列表
        entries_json=""
        for j in $(seq 1 $chapters_per_vol); do
            global_ch=$(($(($i - 1)) * $chapters_per_vol + $j))
            ch_num=$(printf "%03d" $global_ch)
            entries_json="$entries_json\"ch$ch_num\", "
        done
        entries_json="${entries_json%, }"

        cat > "$PROJECT_ROOT/03_内容仓库/04_正文/卷$i/index.json" << EOF
{
    "layer": "正文",
    "project": "$PROJECT_NAME",
    "volume": $i,
    "chapters_per_volume": $chapters_per_vol,
    "created_at": "$(date +%Y-%m-%d)",
    "entries": [$entries_json]
}
EOF
    done

    echo -e "${GREEN}  各层 index.json 生成完成${NC}"
}

#-------------------------------------------------------------------------------
# 更新主控记忆
#-------------------------------------------------------------------------------
update_memory() {
    echo -e "${YELLOW}[4/4] 更新主控记忆...${NC}"

    cat > "$PROJECT_ROOT/memory/MEMORY.md" << EOF
# 灵文 · 主控 Agent 记忆

## 项目状态
- 当前项目：$PROJECT_NAME（🆕 新项目）
- 阶段：PHASE_1_LAUNCH（STEP_01 待启动）
- 总章节数：$CHAPTER_COUNT 章
- 卷数：$VOLUME_COUNT 卷
- 版本：v1.0（初始化）

## 关键文件
- 主控人设：\`CLAUDE.md\`
- 工作流状态：\`workflow_state.json\`
- 执行脚本：\`tools/workflow/run_workflow.sh\`

## 调度命令
- 启动Agent：\`./run_workflow.sh launch <task> <agent> <desc>\`
- 查看任务：\`./run_workflow.sh tasks\`
- 查看状态：\`./run_workflow.sh status\`

## 部门结构
- 灵感部门(3) + 作家部门(10) + 审核部门(10) + 读者部门(20) + 汇总部门(3) = 46 Agent
- 状态机驱动 + 人工重大决策

## 新项目启动流程
1. 灵感部门启动：\`./run_workflow.sh launch\`
2. 工作流自动推进，25步闭环

## 下一步操作
- 启动灵感生成：\`./run_workflow.sh launch inspiration\`
- 或手动进入 STEP_01：\`./run_workflow.sh advance STEP_01\`
EOF

    echo -e "${GREEN}  主控记忆更新完成${NC}"
}

#-------------------------------------------------------------------------------
# 完成
#-------------------------------------------------------------------------------
show_summary() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  灵文 · 项目初始化完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}项目信息:${NC}"
    echo "  项目名称: $PROJECT_NAME"
    echo "  章节数: $CHAPTER_COUNT"
    echo "  卷数: $VOLUME_COUNT"
    echo ""
    echo -e "${YELLOW}下一步操作:${NC}"
    echo "  1. 进入项目目录: cd $PROJECT_ROOT"
    echo "  2. 启动灵感生成: ./run_workflow.sh launch"
    echo "  3. 查看状态: ./run_workflow.sh status"
    echo ""
    echo -e "${YELLOW}目录结构:${NC}"
    echo "  01_灵感库/$PROJECT_NAME/    - 项目灵感文件"
    echo "  03_内容仓库/               - 四层结构（大纲+正文）"
    echo "  06_意见仓库/               - 审核/评论记录"
    echo "  07_汇总仓库/               - 汇总文件"
    echo "  08_已发布/                 - 最终成品"
    echo ""
}

#-------------------------------------------------------------------------------
# 主流程
#-------------------------------------------------------------------------------
main() {
    if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        show_help
        exit 0
    fi

    check_args "$@"
    create_dirs
    init_workflow_state
    generate_indexes
    update_memory
    show_summary
}

main "$@"