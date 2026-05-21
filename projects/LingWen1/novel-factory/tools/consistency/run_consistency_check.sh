#!/bin/bash
#===============================================================================
# 一致性检查统一入口脚本
# 用途：在章节进入审核前进行自动化预检
#===============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 默认值
CHAPTERS_DIR="../../03_内容仓库/04_正文"
OUTPUT_DIR="../../06_意见仓库/07_一致性检查"
SKIP_DUPLICATES=false
REPORT_FILE=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --chapters-dir)
            CHAPTERS_DIR="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --start)
            START_CHAPTER="$2"
            shift 2
            ;;
        --end)
            END_CHAPTER="$2"
            shift 2
            ;;
        --skip-duplicates)
            SKIP_DUPLICATES=true
            shift
            ;;
        --report)
            REPORT_FILE="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --chapters-dir <path>    章节目录 (默认: ../../03_内容仓库/04_正文)"
            echo "  --output-dir <path>     输出目录 (默认: ../../06_意见仓库/07_一致性检查)"
            echo "  --start <num>           起始章节 (默认: 1)"
            echo "  --end <num>             结束章节 (默认: 360)"
            echo "  --skip-duplicates       跳过重复检测 (O(n^2)较慢)"
            echo "  --report <file>         指定报告输出文件"
            echo "  --help, -h              显示帮助"
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            exit 1
            ;;
    esac
done

# 解析章节范围参数
START_CHAPTER="${START_CHAPTER:-1}"
END_CHAPTER="${END_CHAPTER:-360}"

echo -e "${BLUE}=== 自动化一致性检查 ===${NC}"
echo ""
echo "章节目录: $CHAPTERS_DIR"
echo "输出目录: $OUTPUT_DIR"
echo "检查范围: ch$(printf '%03d' $START_CHAPTER)-ch$(printf '%03d' $END_CHAPTER)"
echo ""

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 构建命令
PYTHON_CMD="python3 auto_consistency_checker.py '$CHAPTERS_DIR'"
PYTHON_CMD="$PYTHON_CMD --start $START_CHAPTER --end $END_CHAPTER"
PYTHON_CMD="$PYTHON_CMD --output '$OUTPUT_DIR'"

if [ "$SKIP_DUPLICATES" = true ]; then
    PYTHON_CMD="$PYTHON_CMD --skip-duplicates"
fi

if [ -n "$REPORT_FILE" ]; then
    PYTHON_CMD="$PYTHON_CMD --report '$REPORT_FILE'"
fi

# 执行检查
echo -e "${BLUE}开始检查...${NC}"
echo ""

eval $PYTHON_CMD
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ 检查通过 - 未发现一致性问题${NC}"
else
    echo -e "${RED}❌ 检查失败 - 发现问题，请查看报告${NC}"
fi

echo ""
echo "报告目录: $OUTPUT_DIR"

exit $EXIT_CODE