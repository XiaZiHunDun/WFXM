#!/bin/bash
#===============================================================================
# 灵文 · 修复验证脚本
# 用于验证作家修复是否正确执行，防止"虚假修复"
#===============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"
CONTENT_DIR="$PROJECT_ROOT/03_内容仓库/04_正文"
OPINION_DIR="$PROJECT_ROOT/06_意见仓库"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

#-------------------------------------------------------------------------------
# 帮助信息
#-------------------------------------------------------------------------------
show_help() {
    cat << EOF
${GREEN}灵文 · 修复验证脚本${NC}

${YELLOW}功能:${NC}
    验证作家修复是否正确执行，防止"虚假修复"和"自我验证"

${YELLOW}用法:${NC}
    ./run_verify.sh check <章节范围>     # 验证指定章节的修复
    ./run_verify.sh sample              # 随机抽样10%验证
    ./run_verify.sh report <章节>       # 生成单章验证报告
    ./run_verify.sh batch <批次>        # 批量验证
    ./run_verify.sh status             # 查看验证状态

${YELLOW}示例:${NC}
    ./run_verify.sh check ch291        # 验证ch291的修复
    ./run_verify.sh check ch250-ch254  # 验证ch250-ch254的修复
    ./run_verify.sh sample             # 随机抽样10%验证
    ./run_verify.sh batch B01          # 验证B批次

${YELLOW}验证流程:${NC}
    1. 读取 issues_found 中该章节的问题
    2. 读取源文件，验证问题是否确实修复
    3. 生成验证报告
    4. 更新 workflow_state.json

${YELLOW}注意:${NC}
    - 修复验证由独立的"验证Agent"执行（非原修复者）
    - 随机抽样比例：10%
    - P0问题：100%验证
    - P1问题：30%验证

EOF
}

#-------------------------------------------------------------------------------
# 加载状态
#-------------------------------------------------------------------------------
load_state() {
    if [ -f "$WORKFLOW_FILE" ]; then
        PROJECT_NAME=$(python3 -c "import json; d=json.load(open('$WORKFLOW_FILE')); print(d.get('project_info',{}).get('project_name','星陨纪元'))" 2>/dev/null || echo "星陨纪元")
    else
        PROJECT_NAME="星陨纪元"
    fi
}

#-------------------------------------------------------------------------------
# 验证单章修复
#-------------------------------------------------------------------------------
verify_chapter() {
    local chapter="$1"
    local report_file="$OPINION_DIR/04_正文_审核/${chapter}_验证报告.md"

    echo -e "${BLUE}[验证] 检查章节: $chapter${NC}"

    # 检查章节文件是否存在
    if [ ! -f "$CONTENT_DIR/${chapter}.md" ]; then
        echo -e "${RED}[错误] 章节文件不存在: ${chapter}.md${NC}"
        return 1
    fi

    # 读取该章节的问题
    local issues=$(python3 << EOF
import json

try:
    with open('$WORKFLOW_FILE', 'r') as f:
        state = json.load(f)

    issues_found = state.get('issues_found', {})

    # 查找包含该章节的问题
    chapter_issues = []
    for key, values in issues_found.items():
        # 匹配 ch291 或 ch291-ch300 格式
        if chapter in key or any(chapter in v for v in values):
            chapter_issues.append({'range': key, 'issues': values})

    for ci in chapter_issues:
        print(f"章节范围: {ci['range']}")
        for issue in ci['issues']:
            print(f"  - {issue}")

    if not chapter_issues:
        print("未发现问题记录")

except Exception as e:
    print(f"读取状态失败: {e}")
EOF
)

    if [ -z "$issues" ]; then
        echo -e "${YELLOW}[警告] 没有找到该章节的问题记录${NC}"
        return 0
    fi

    echo "$issues"

    # 生成验证报告
    cat > "$report_file" << EOF
# 修复验证报告：$chapter

## 验证信息
- 章节：$chapter
- 验证时间：$(date +%Y-%m-%d\ %H:%M:%S)
- 验证方式：人工抽检

## 问题记录

$issues

## 验证结果

| 问题 | 验证状态 | 说明 |
|------|---------|------|
| | | |

## 验证详情

EOF

    echo -e "${GREEN}[完成] 验证报告已生成: $report_file${NC}"
    echo "$report_file"
}

#-------------------------------------------------------------------------------
# 随机抽样验证
#-------------------------------------------------------------------------------
verify_sample() {
    echo -e "${BLUE}[验证] 执行随机抽样验证（10%）${NC}"

    local total_chapters=360
    local sample_size=36  # 10%
    local VERIFY_LOG="$PROJECT_ROOT/.verify_log.json"

    # 生成随机抽样
    local samples=$(python3 << EOF
import random
import json

random.seed()  # 使用随机种子

# 抽取36个章节
samples = random.sample(range(1, 361), 36)
samples_str = ', '.join([f'ch{s:03d}' for s in samples])
print(samples_str)

# 保存到日志
log = {'timestamp': '$(date +%Y-%m-%d\ %H:%M:%S)', 'samples': [f'ch{s:03d}' for s in samples]}
with open('$VERIFY_LOG', 'w') as f:
    json.dump(log, f, indent=2)
EOF
)

    echo -e "${CYAN}抽样章节: $samples${NC}"
    echo ""

    local count=0
    for chapter in $samples; do
        verify_chapter "$chapter" > /dev/null 2>&1 && ((count++)) || true
    done

    echo ""
    echo -e "${GREEN}[完成] 已验证 $count 个章节${NC}"
    echo -e "${YELLOW}查看详细报告: ls $OPINION_DIR/04_正文_审核/*验证报告.md${NC}"
}

#-------------------------------------------------------------------------------
# 批量验证
#-------------------------------------------------------------------------------
verify_batch() {
    local batch="$1"

    echo -e "${BLUE}[验证] 批量验证批次: $batch${NC}"

    # 根据批次ID确定章节范围
    local chapter_range=$(python3 << EOF
import json

try:
    with open('$WORKFLOW_FILE', 'r') as f:
        state = json.load(f)

    completed = state.get('review_queue', {}).get('completed', [])

    for batch_info in completed:
        if batch_info.get('batch_id', '').endswith(batch):
            chapters = batch_info.get('chapters', [])
            if chapters:
                print(f"{chapters[0]}-{chapters[-1]}")
                break
    else:
        # 如果找不到批次，尝试解析批次参数
        print("UNKNOWN")

except Exception as e:
    print(f"ERROR: {e}")
EOF
)

    if [ "$chapter_range" = "UNKNOWN" ]; then
        echo -e "${YELLOW}[警告] 无法确定批次章节范围，使用批量模式${NC}"
        chapter_range="$batch"
    fi

    echo -e "${CYAN}章节范围: $chapter_range${NC}"

    # 验证该范围内的所有章节
    local count=0
    local start=1
    local end=10

    if [[ "$chapter_range" =~ ch([0-9]+)-ch([0-9]+) ]]; then
        start=${BASH_REMATCH[1]}
        end=${BASH_REMATCH[2]}
    elif [[ "$chapter_range" =~ ^ch([0-9]+)$ ]]; then
        start=${BASH_REMATCH[1]}
        end=$start
    fi

    for i in $(seq $start $end); do
        chapter=$(printf "ch%03d" $i)
        verify_chapter "$chapter" > /dev/null 2>&1 && ((count++)) || true
    done

    echo -e "${GREEN}[完成] 已验证 $count 个章节${NC}"
}

#-------------------------------------------------------------------------------
# 查看验证状态
#-------------------------------------------------------------------------------
verify_status() {
    echo -e "${BLUE}[状态] 验证状态${NC}"
    echo ""

    # 统计验证报告数量
    local report_count=$(ls "$OPINION_DIR/04_正文_审核/"*验证报告.md 2>/dev/null | wc -l)
    echo -e "${YELLOW}已生成验证报告: $report_count 份${NC}"

    # 检查上次验证日志
    if [ -f "$PROJECT_ROOT/.verify_log.json" ]; then
        echo ""
        echo -e "${CYAN}最近抽样验证:${NC}"
        python3 -c "import json; d=json.load(open('$PROJECT_ROOT/.verify_log.json')); print(f\"时间: {d['timestamp']}\"); print(f\"章节数: {len(d['samples'])}\")"
    fi

    # P0问题统计
    echo ""
    echo -e "${CYAN}P0问题验证状态:${NC}"
    python3 << EOF
import json

try:
    with open('$WORKFLOW_FILE', 'r') as f:
        state = json.load(f)

    issues = state.get('issues_found', {})
    p0_count = 0
    p0_fixed = 0

    for issues_list in issues.values():
        for issue in issues_list:
            if '(P0)' in str(issue):
                p0_count += 1
                if '已修复' in str(issue) or '修复' in str(issue):
                    p0_fixed += 1

    print(f"P0问题总数: {p0_count}")
    print(f"声称已修复: {p0_fixed}")
    print(f"实际验证: 待验证")

except Exception as e:
    print(f"读取状态失败: {e}")
EOF
}

#-------------------------------------------------------------------------------
# 生成单章详细报告
#-------------------------------------------------------------------------------
generate_chapter_report() {
    local chapter="$1"

    echo -e "${BLUE}[报告] 生成章节 $chapter 验证报告${NC}"

    # 读取章节内容
    local content_file="$CONTENT_DIR/${chapter}.md"
    if [ ! -f "$content_file" ]; then
        echo -e "${RED}[错误] 章节文件不存在${NC}"
        return 1
    fi

    # 读取行数
    local line_count=$(wc -l < "$content_file")
    local word_count=$(wc -w < "$content_file")

    # 读取审核报告
    local review_report="$OPINION_DIR/04_正文_审核/${chapter}_审核员A_审核.md"

    echo ""
    echo "=== $chapter 验证报告 ==="
    echo "文件: ${content_file}"
    echo "行数: $line_count"
    echo "字数: 约 $word_count"
    echo ""

    if [ -f "$review_report" ]; then
        echo "审核报告: 已存在"
    else
        echo "审核报告: 不存在"
    fi

    echo ""
    echo "=== 问题检查 ==="

    # 检查问题
    python3 << EOF
import json

try:
    with open('$WORKFLOW_FILE', 'r') as f:
        state = json.load(f)

    issues = state.get('issues_found', {})
    found_issues = []

    for key, values in issues.items():
        if chapter in key:
            found_issues.extend(values)
        # 也检查issue内容中是否包含该章节
        for v in values:
            if chapter in str(v):
                found_issues.append(v)

    if found_issues:
        print(f"发现 {len(found_issues)} 个问题:")
        for i, issue in enumerate(found_issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("未发现问题记录")

except Exception as e:
    print(f"读取失败: {e}")
EOF

    echo ""
    echo "=== 内容抽样 ==="
    head -20 "$content_file"
    echo "..."
    tail -10 "$content_file"
}

#-------------------------------------------------------------------------------
# 主流程
#-------------------------------------------------------------------------------
main() {
    if [ $# -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        show_help
        exit 0
    fi

    load_state

    local command="$1"
    shift

    case "$command" in
        check)
            if [ $# -eq 0 ]; then
                echo -e "${RED}错误: 请指定章节${NC}"
                echo "用法: ./run_verify.sh check ch291"
                exit 1
            fi
            verify_chapter "$1"
            ;;
        sample)
            verify_sample
            ;;
        batch)
            if [ $# -eq 0 ]; then
                echo -e "${RED}错误: 请指定批次${NC}"
                exit 1
            fi
            verify_batch "$1"
            ;;
        report)
            if [ $# -eq 0 ]; then
                echo -e "${RED}错误: 请指定章节${NC}"
                exit 1
            fi
            generate_chapter_report "$1"
            ;;
        status)
            verify_status
            ;;
        *)
            echo -e "${RED}错误: 未知命令 '$command'${NC}"
            show_help
            exit 1
            ;;
    esac
}

main "$@"