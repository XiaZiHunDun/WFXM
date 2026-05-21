#!/bin/bash
#===============================================================================
# 发布管理脚本
# 用途：发布前检查、版本归档、版本列表、版本对比
#===============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 切换到 novel-factory 根目录（而非脚本所在目录）
cd "$(dirname "$(dirname "$SCRIPT_DIR")")"

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
    echo -e "${BLUE}发布管理脚本${NC}"
    echo ""
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  check <版本>     发布前检查（例如: check v1.0）"
    echo "  preflight        只读预检（读 workflow 版本，不创建目录）"
    echo "  check-naming     检查章节文件命名是否正确"
    echo "  archive <版本>   归档指定版本（例如: archive v1.0）"
    echo "  merge <版本>     合并360章正文为单文件（例如: merge v3.0）"
    echo "  list             列出所有发布版本"
    echo "  diff <版本1> <版本2>  对比两个版本（例如: diff v1.0 v2.0）"
    echo ""
    echo "合并选项:"
    echo "  --all             合并全部360章（默认）"
    echo "  --range <start-end>  合并指定范围（如 --range 1-120）"
    echo ""
    echo "示例:"
    echo "  $0 check v1.0"
    echo "  $0 check-naming"
    echo "  $0 archive v1.0"
    echo "  $0 merge v3.0"
    echo "  $0 merge v3.0 --range 1-120"
    echo "  $0 list"
    echo "  $0 diff v1.0 v2.0"
}

#-------------------------------------------------------------------------------
# 检查函数
#-------------------------------------------------------------------------------
do_check() {
    local version="$1"

    if [[ -z "$version" ]]; then
        echo -e "${RED}错误: 请指定版本号，例如: check v1.0${NC}"
        exit 1
    fi

    echo -e "${BLUE}=== 发布前检查: $version ===${NC}"
    echo ""

    # 检查工作流状态文件
    echo -e "${YELLOW}[1/8] 检查工作流状态文件...${NC}"
    if [[ ! -f "workflow_state.json" ]]; then
        echo -e "${RED}  ✗ workflow_state.json 不存在${NC}"
        exit 1
    fi
    echo -e "${GREEN}  ✓ workflow_state.json 存在${NC}"

    # 检查状态是否为完成
    echo -e "${YELLOW}[2/8] 检查项目状态...${NC}"
    local phase=$(grep -o '"current_phase"[[:space:]]*:[[:space:]]*"[^"]*"' workflow_state.json | cut -d'"' -f4)
    if [[ "$phase" == "PHASE_COMPLETE" ]]; then
        echo -e "${GREEN}  ✓ 项目状态: PHASE_COMPLETE${NC}"
    else
        echo -e "${YELLOW}  ⚠ 项目状态: $phase（应为 PHASE_COMPLETE）${NC}"
    fi

    # 检查审核完成情况
    echo -e "${YELLOW}[3/8] 检查审核完成情况...${NC}"
    if [[ -d "06_意见仓库/04_正文_审核" ]]; then
        local audit_count=$(ls 06_意见仓库/04_正文_审核/*_审核.md 2>/dev/null | wc -l)
        echo -e "${GREEN}  ✓ 审核报告数量: $audit_count${NC}"
    else
        echo -e "${RED}  ✗ 审核报告目录不存在${NC}"
    fi

    # 检查汇总文件（正文合并产出）
    echo -e "${YELLOW}[4/8] 检查汇总文件...${NC}"
    local stage_count=$(ls "07_汇总仓库/阶段正文"/*.md 2>/dev/null | wc -l)
    local vol_count=$(ls "07_汇总仓库/卷正文"/*.md 2>/dev/null | wc -l)
    local full_count=$(ls "07_汇总仓库/全文正文"/*.md 2>/dev/null | wc -l)
    if [[ "$full_count" -gt 0 ]]; then
        echo -e "${GREEN}  ✓ 汇总文件: ${stage_count}阶段 + ${vol_count}卷 + ${full_count}全文${NC}"
    else
        echo -e "${RED}  ✗ 汇总文件不完整${NC}"
    fi

    # 检查已发布目录
    echo -e "${YELLOW}[5/8] 检查已发布目录...${NC}"
    if [[ ! -d "08_已发布" ]]; then
        if [[ "${READONLY_PREFLIGHT:-0}" == "1" ]]; then
            echo -e "${YELLOW}  ⚠ 08_已发布 目录不存在（只读预检不创建）${NC}"
        else
            mkdir -p "08_已发布"
            echo -e "${YELLOW}  ⚠ 已创建 08_已发布 目录${NC}"
        fi
    else
        echo -e "${GREEN}  ✓ 08_已发布 目录存在${NC}"
    fi

    # 检查未解决意见
    echo -e "${YELLOW}[6/8] 检查未解决意见...${NC}"
    if grep -q "unresolved_issues" workflow_state.json 2>/dev/null; then
        local issues=$(grep -o '"unresolved_issues"[[:space:]]*:[[:space:]]*[0-9]*' workflow_state.json | grep -o '[0-9]*')
        if [[ -n "$issues" && "$issues" -le 5 ]]; then
            echo -e "${GREEN}  ✓ 未解决意见: $issues（≤5，通过）${NC}"
        elif [[ -n "$issues" ]]; then
            echo -e "${RED}  ✗ 未解决意见: $issues（>5，不通过）${NC}"
        fi
    else
        echo -e "${YELLOW}  ⚠ 无法读取未解决意见数量${NC}"
    fi

    # 检查 P0（读最新一致性 JSON，避免 grep「P0」误报）
    echo -e "${YELLOW}[7/8] 检查一致性 P0（最新 JSON 报告）...${NC}"
    local consistency_script="${SCRIPT_DIR}/../consistency/read_latest_report.py"
    local sev_line=""
    if [[ -f "$consistency_script" ]]; then
        sev_line="$(python3 "$consistency_script" "$(pwd)" 2>/dev/null)" || true
    fi
    if [[ "$sev_line" == "MISSING" || -z "$sev_line" ]]; then
        echo -e "${YELLOW}  ⚠ 无 consistency_check_*.json（可先运行 consistency-weekly）${NC}"
    else
        local p0_count p1_count report_rel
        read -r p0_count p1_count _ _ report_rel <<< "$sev_line"
        if [[ "${p0_count:-0}" -eq 0 ]]; then
            if [[ "${p1_count:-0}" -eq 0 ]]; then
                echo -e "${GREEN}  ✓ P0=0 P1=0（报告: ${report_rel}）${NC}"
            else
                echo -e "${YELLOW}  ⚠ P0=0 P1=${p1_count} 有条件通过（报告: ${report_rel}）${NC}"
            fi
        else
            echo -e "${RED}  ✗ P0=${p0_count}（报告: ${report_rel}）须修复后再发布${NC}"
        fi
    fi

    # 检查版本文件是否存在
    echo -e "${YELLOW}[8/8] 检查版本文件...${NC}"
    local version_file=$(find "08_已发布" -name "*_${version}_*.md" -o -name "*${version}*.md" 2>/dev/null | head -1)
    if [[ -n "$version_file" ]]; then
        echo -e "${GREEN}  ✓ 版本文件存在: $version_file${NC}"
    else
        echo -e "${YELLOW}  ⚠ 版本文件不存在（将在发布时创建）${NC}"
    fi

    echo ""
    echo -e "${BLUE}=== 检查完成 ===${NC}"
    echo "如需发布，请确保上述检查全部通过后执行归档操作"
}

#-------------------------------------------------------------------------------
# 只读预检（Runtime publish-preflight）
#-------------------------------------------------------------------------------
do_preflight() {
    local version=""
    if [[ -f "workflow_state.json" ]]; then
        version=$(grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' workflow_state.json | head -1 | cut -d'"' -f4)
    fi
    if [[ -z "$version" ]]; then
        version="v3.0"
        echo -e "${YELLOW}未从 workflow_state.json 读取版本，默认 ${version}${NC}"
    fi
    echo -e "${BLUE}=== 发布前只读预检: ${version} ===${NC}"
    READONLY_PREFLIGHT=1 do_check "$version"
}

#-------------------------------------------------------------------------------
# 归档函数
#-------------------------------------------------------------------------------
do_archive() {
    local version="$1"

    if [[ -z "$version" ]]; then
        echo -e "${RED}错误: 请指定版本号，例如: archive v1.0${NC}"
        exit 1
    fi

    echo -e "${BLUE}=== 归档版本: $version ===${NC}"
    echo ""

    # 获取项目信息
    local project_name="星陨纪元"
    local project_status="unknown"
    local emotion_quality="unknown"
    local total_chapters="360"

    if [[ -f "workflow_state.json" ]]; then
        project_name=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' workflow_state.json | head -1 | cut -d'"' -f4)
        project_name=${project_name:-"星陨纪元"}
        emotion_quality=$(grep -o '"emotion_quality"[[:space:]]*:[[:space:]]*"[^"]*"' workflow_state.json | cut -d'"' -f4)
        emotion_quality=${emotion_quality:-"unknown"}
        total_chapters=$(grep -o '"total_chapters"[[:space:]]*:[[:space:]]*[0-9]*' workflow_state.json | grep -o '[0-9]*')
        total_chapters=${total_chapters:-"360"}
    fi

    # 查找要归档的源文件（优先全文正文目录）
    local source_files=()

    # 策略1：从07_汇总仓库/全文正文/ 查找
    if [[ -d "07_汇总仓库/全文正文" ]]; then
        local full_text=$(find "07_汇总仓库/全文正文" -name "*${version}*.md" 2>/dev/null | head -1)
        if [[ -n "$full_text" && -f "$full_text" ]]; then
            source_files+=("$full_text")
        fi
    fi

    # 策略2：从07_汇总仓库/汇总报告/ 查找
    if [[ -d "07_汇总仓库/汇总报告" ]]; then
        local report_files=$(find "07_汇总仓库/汇总报告" -name "*${version}*.md" 2>/dev/null)
        for f in $report_files; do
            source_files+=("$f")
        done
    fi

    # 策略3：从07_汇总仓库/ 查找汇总文件
    if [[ ${#source_files[@]} -eq 0 && -d "07_汇总仓库" ]]; then
        local fallback=$(find "07_汇总仓库" -name "*汇总*.md" -o -name "*终稿*.md" 2>/dev/null | head -3)
        for f in $fallback; do
            source_files+=("$f")
        done
    fi

    if [[ ${#source_files[@]} -eq 0 ]]; then
        echo -e "${RED}错误: 无法找到要归档的文件${NC}"
        exit 1
    fi

    echo -e "${YELLOW}[1/6] 源文件:${NC}"
    for f in "${source_files[@]}"; do
        echo "  - $f"
    done

    # 创建归档目录
    local archive_date=$(date +%Y%m%d)
    local archive_dir="08_已发布/归档/${project_name}_${version}_${archive_date}"

    echo -e "${YELLOW}[2/6] 创建归档目录: $archive_dir${NC}"
    mkdir -p "$archive_dir"

    # 复制文件到归档目录
    echo -e "${YELLOW}[3/6] 复制文件到归档目录...${NC}"
    local copied=0
    for f in "${source_files[@]}"; do
        if [[ -f "$f" ]]; then
            cp "$f" "$archive_dir/"
            copied=$((copied + 1))
        fi
    done
    echo -e "${GREEN}  ✓ 复制完成: $copied 个文件${NC}"

    # 验证归档完整性
    echo -e "${YELLOW}[4/6] 验证归档完整性...${NC}"
    local full_text_in_archive=$(find "$archive_dir" -name "*全文*" -o -name "*正文*" 2>/dev/null | head -1)
    local verify_passed=true

    if [[ -n "$full_text_in_archive" ]]; then
        local file_size=$(stat -c%s "$full_text_in_archive" 2>/dev/null || stat -f%z "$full_text_in_archive" 2>/dev/null)
        local size_mb=$((file_size / 1024 / 1024))
        if [[ $size_mb -lt 1 ]]; then
            echo -e "${YELLOW}  ⚠ 警告: 全文文件较小 (${size_mb}MB)，可能不完整${NC}"
        else
            echo -e "${GREEN}  ✓ 全文文件大小: ${size_mb}MB${NC}"
        fi
    else
        echo -e "${YELLOW}  ⚠ 未找到全文正文文件${NC}"
    fi

    # 统计归档内容
    local total_lines=0
    local file_count=0
    for f in "$archive_dir"/*.md; do
        if [[ -f "$f" ]]; then
            local lines=$(wc -l < "$f" 2>/dev/null || echo 0)
            total_lines=$((total_lines + lines))
            file_count=$((file_count + 1))
        fi
    done

    echo -e "${YELLOW}[5/6] 归档统计:${NC}"
    echo "  - 文件数: $file_count"
    echo "  - 总行数: $total_lines"

    # 创建发布记录
    echo -e "${YELLOW}[6/6] 创建发布记录...${NC}"
    local primary_source="${source_files[0]}"
    cat > "$archive_dir/发布记录.md" << EOF
# 发布记录：${project_name} ${version}

## 基本信息
- 版本：${version}
- 发布日期：$(date +%Y-%m-%d)
- 发布人：主控Agent
- 发布原因：终版发布

## 内容概述
- 项目名称：${project_name}
- 总章节数：${total_chapters}章
- 归档总行数：约${total_lines}行
- 质量评级：${emotion_quality}
- 主要源文件：${primary_source}

## 归档内容
$(for f in "${source_files[@]}"; do echo "- $(basename "$f")"; done)

## 归档信息
- 归档日期：$(date +%Y-%m-%d)
- 归档位置：${archive_dir}
- 归档原因：版本发布归档
EOF

    echo ""
    echo -e "${GREEN}=== 归档完成 ===${NC}"
    echo "归档位置: $archive_dir"
    echo "归档文件: $file_count 个"
    echo "总行数: $total_lines"
}

#-------------------------------------------------------------------------------
# 列表函数
#-------------------------------------------------------------------------------
do_list() {
    echo -e "${BLUE}=== 发布版本列表 ===${NC}"
    echo ""

    # 当前版本
    echo -e "${YELLOW}当前版本:${NC}"
    if [[ -d "08_已发布" ]]; then
        ls -la "08_已发布"/*.md 2>/dev/null | while read line; do
            echo "  $line"
        done
    fi

    echo ""

    # 归档版本
    echo -e "${YELLOW}归档版本:${NC}"
    if [[ -d "08_已发布/归档" ]]; then
        find "08_已发布/归档" -type d -name "*_v*" 2>/dev/null | while read dir; do
            echo "  $(basename "$dir")"
        done
    else
        echo "  （暂无归档版本）"
    fi
}

#-------------------------------------------------------------------------------
# 对比函数
#-------------------------------------------------------------------------------
do_diff() {
    local version1="$1"
    local version2="$2"

    if [[ -z "$version1" || -z "$version2" ]]; then
        echo -e "${RED}错误: 请指定两个版本号，例如: diff v1.0 v2.0${NC}"
        exit 1
    fi

    echo -e "${BLUE}=== 版本对比: $version1 vs $version2 ===${NC}"
    echo ""

    # 查找版本文件
    local file1=$(find "08_已发布" -name "*_${version1}_*.md" -o -name "*${version1}*.md" 2>/dev/null | grep -v "/归档/" | head -1)
    local file2=$(find "08_已发布" -name "*_${version2}_*.md" -o -name "*${version2}*.md" 2>/dev/null | grep -v "/归档/" | head -1)

    # 检查归档目录
    if [[ -z "$file1" ]]; then
        file1=$(find "08_已发布/归档" -name "*_${version1}_*" -name "*.md" 2>/dev/null | head -1)
    fi
    if [[ -z "$file2" ]]; then
        file2=$(find "08_已发布/归档" -name "*_${version2}_*" -name "*.md" 2>/dev/null | head -1)
    fi

    echo -e "${YELLOW}版本1文件:${NC} ${file1:-（未找到）}"
    echo -e "${YELLOW}版本2文件:${NC} ${file2:-（未找到）}"
    echo ""

    if [[ -z "$file1" || -z "$file2" ]]; then
        echo -e "${RED}错误: 无法找到两个版本的对比文件${NC}"
        exit 1
    fi

    # 对比基本信息
    echo -e "${YELLOW}基本信息对比:${NC}"
    local lines1=$(wc -l < "$file1")
    local lines2=$(wc -l < "$file2")
    local words1=$(wc -w < "$file1")
    local words2=$(wc -w < "$file2")

    echo "  $version1: $lines1 行, 约 $words1 字"
    echo "  $version2: $lines2 行, 约 $words2 字"
    echo "  差异: $((lines2 - lines1)) 行, $((words2 - words1)) 字"
    echo ""

    # 对比章节结构（如果包含章节信息）
    if grep -q "ch[0-9]" "$file1" || grep -q "ch[0-9]" "$file2"; then
        echo -e "${YELLOW}章节对比:${NC}"
        local ch1_count=$(grep -oE 'ch[0-9]+' "$file1" | sort -u | wc -l)
        local ch2_count=$(grep -oE 'ch[0-9]+' "$file2" | sort -u | wc -l)
        echo "  $version1 涉及章节: $ch1_count 个"
        echo "  $version2 涉及章节: $ch2_count 个"
        echo ""
    fi

    # 使用diff命令对比内容
    echo -e "${YELLOW}内容差异（行号）:${NC}"
    diff -y --width=80 "$file1" "$file2" | head -50 || true
}

#-------------------------------------------------------------------------------
# 合并函数（v2.0新增）
#-------------------------------------------------------------------------------
do_merge() {
    local version="$1"
    shift
    local range_start=""
    local range_end=""

    if [[ -z "$version" ]]; then
        echo -e "${RED}错误: 请指定版本号，例如: merge v3.0${NC}"
        exit 1
    fi

    echo -e "${BLUE}=== 合并正文: $version ===${NC}"
    echo ""

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --range)
                if [[ "$2" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                    range_start="${BASH_REMATCH[1]}"
                    range_end="${BASH_REMATCH[2]}"
                else
                    echo -e "${RED}错误: --range 格式应为 1-120${NC}"
                    exit 1
                fi
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # 获取项目名
    local project_name=""
    if [[ -f "workflow_state.json" ]]; then
        project_name=$(grep -o '"project_name"[[:space:]]*:[[:space:]]*"[^"]*"' workflow_state.json | cut -d'"' -f4)
    fi
    project_name=${project_name:-"星陨纪元"}

    # 设置输出目录和文件
    local output_dir="08_已发布"
    local output_file=""

    if [[ -n "$range_start" && -n "$range_end" ]]; then
        output_file="${output_dir}/${project_name}_正文_${version}_ch${range_start}-ch${range_end}.md"
        echo -e "${YELLOW}[1/5] 合并范围: ch${range_start}-ch${range_end}${NC}"
    else
        output_file="${output_dir}/${project_name}_全文正文_${version}.md"
        echo -e "${YELLOW}[1/5] 合并范围: 全部360章${NC}"
    fi

    echo -e "${YELLOW}[2/5] 输出文件: $output_file${NC}"

    # 清空输出文件（如存在）
    > "$output_file"

    # 获取章节列表（按标题章节号排序）
    local chapter_dir="03_内容仓库/04_正文"
    local chapters=()
    local missing_chapters=()
    local naming_issues=()
    local expected_start=0
    local expected_end=360

    echo -e "${YELLOW}[3/5] 扫描并按标题章节号排序...${NC}"

    # 使用Python提取章节号并排序
    python3 << 'PYTHON_SCRIPT' > /tmp/merge_sorted.txt
import re
import os

def extract_chapter_num(title):
    """从标题提取章节号 - 正确版本"""
    match = re.search(r'第([零一二三四五六七八九十百]+)章', title)
    if not match:
        return None
    zh = match.group(1)
    digit_map = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    if zh == '零':
        return 0
    if '百' in zh:
        parts = zh.split('百', 1)
        hundred_part = parts[0] if parts[0] else '一'
        rest = parts[1] if len(parts) > 1 else ''
        hundred_val = digit_map.get(hundred_part, 1) * 100
        if not rest:
            return hundred_val
        # Check for "一十", "二十" etc pattern at start of rest
        if len(rest) >= 2 and rest[0] in digit_map and rest[1] == '十':
            tens_digit = digit_map.get(rest[0], 0)
            ones_digit = digit_map.get(rest[2], 0) if len(rest) > 2 else 0
            return hundred_val + tens_digit * 10 + ones_digit
        elif rest.startswith('十'):
            if len(rest) == 1:
                return hundred_val + 10
            else:
                return hundred_val + 10 + digit_map.get(rest[1], 0)
        else:
            result = 0
            for char in rest:
                if char == '十':
                    break
                if char in digit_map:
                    result = result * 10 + digit_map[char]
            return hundred_val + result
    else:
        if zh.startswith('十'):
            if len(zh) == 1:
                return 10
            return 10 + digit_map.get(zh[1], 0)
        if zh.endswith('十') and len(zh) == 2:
            return digit_map.get(zh[0], 0) * 10
        result = 0
        for char in zh:
            if char in digit_map:
                result = result * 10 + digit_map[char]
        return result

chapter_dir = "03_内容仓库/04_正文"
chapter_files = []

for i in range(0, 361):
    fname = f"ch{i:03d}.md"
    fpath = os.path.join(chapter_dir, fname)
    if not os.path.exists(fpath):
        print(f"MISSING:{i}")
        continue
    with open(fpath, 'r') as f:
        first_line = f.readline().strip()
    title_num = extract_chapter_num(first_line)
    if title_num is None:
        print(f"NAMING_ISSUE:{i}:NONE:{first_line[:50]}")
        continue
    # 输出: 标题章节号:文件编号:文件名
    print(f"{title_num}:{i}:{fname}:{first_line[:50]}")

PYTHON_SCRIPT

    # 解析Python输出
    declare -A title_to_files
    while IFS=: read -r title_num file_num fname line; do
        if [[ "$title_num" == "MISSING" ]]; then
            missing_chapters+=("$file_num")
        elif [[ "$title_num" == "NAMING_ISSUE" ]]; then
            naming_issues+=("${file_num}:${line}")
        else
            # 按标题章节号存储
            title_to_files[$title_num]="$chapter_dir/$fname"
        fi
    done < /tmp/merge_sorted.txt

    # 检查缺失章节
    local total_missing=${#missing_chapters[@]}
    echo -e "${YELLOW}  扫描完成${NC}"

    if [[ $total_missing -gt 0 ]]; then
        echo -e "${YELLOW}  ⚠ 文件缺失: ${missing_chapters[*]}${NC}"
    fi

    # 检查命名问题
    if [[ ${#naming_issues[@]} -gt 0 ]]; then
        echo -e "${YELLOW}  ⚠ 命名问题: ${#naming_issues[@]} 个文件${NC}"
    fi

    # 按标题章节号排序合并
    local sorted_chapters=()
    for title_num in $(echo "${!title_to_files[@]}" | tr ' ' '\n' | sort -n); do
        sorted_chapters+=("${title_to_files[$title_num]}")
    done

    local total_chapters=${#sorted_chapters[@]}
    echo -e "${YELLOW}[4/5] 找到 $total_chapters 个章节文件（按标题排序）${NC}"

    if [[ $total_chapters -eq 0 ]]; then
        echo -e "${RED}错误: 未找到任何章节文件${NC}"
        exit 1
    fi

    # 合并文件
    echo -e "${YELLOW}[5/5] 合并中...${NC}"
    local merged=0
    for chapter in "${sorted_chapters[@]}"; do
        # 提取标题中的章节号作为分隔符
        local chapter_num=$(basename "$chapter" .md | sed 's/ch//')
        echo -e "\n\n---\n\n# 第${chapter_num}章\n\n" >> "$output_file"
        # 添加章节内容
        cat "$chapter" >> "$output_file"
        merged=$((merged + 1))
        if [[ $((merged % 50)) -eq 0 ]]; then
            echo -e "  已合并: $merged / $total_chapters"
        fi
    done

    # 验证结果
    local lines=$(wc -l < "$output_file")
    local size=$(du -h "$output_file" | cut -f1)

    echo ""
    echo -e "${GREEN}=== 合并完成 ===${NC}"
    echo "输出文件: $output_file"
    echo "合并章节: $total_chapters 个"
    echo "总行数: $lines"
    echo "文件大小: $size"

    if [[ $total_missing -gt 0 ]]; then
        echo ""
        echo -e "${YELLOW}⚠ 警告: 文件缺失 $total_missing 个${NC}"
        echo -e "${YELLOW}  缺失文件编号: ${missing_chapters[*]}${NC}"
    fi

    if [[ ${#naming_issues[@]} -gt 0 ]]; then
        echo ""
        echo -e "${YELLOW}⚠ 警告: ${#naming_issues[@]} 个文件命名有问题${NC}"
    fi

    # 更新workflow_state.json（如需要）
    if [[ -f "workflow_state.json" ]]; then
        echo -e "${YELLOW}[可选] 更新workflow_state.json的merged_file字段${NC}"
    fi
}

#-------------------------------------------------------------------------------
# 主程序
#-------------------------------------------------------------------------------
case "${1:-}" in
    preflight)
        do_preflight
        ;;
    check)
        do_check "$2"
        ;;
    check-naming)
        bash "$SCRIPT_DIR/run_check_naming.sh"
        ;;
    archive)
        do_archive "$2"
        ;;
    merge)
        do_merge "$2" "$3" "$4" "$5"
        ;;
    list)
        do_list
        ;;
    diff)
        do_diff "$2" "$3"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}错误: 未知命令 '$1'${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac