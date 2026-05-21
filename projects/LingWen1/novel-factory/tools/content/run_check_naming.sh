#!/bin/bash
#===============================================================================
# 章节文件命名校验脚本 v2.0
# 用途：检查文件命名是否与内容章节号一致
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

echo -e "${BLUE}=== 章节文件命名校验 v2.0 ===${NC}"
echo ""

# 使用Python进行校验
python3 << 'PYTHON_SCRIPT'
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
issues = []
missing_files = []
covered_chapters = set()
duplicate_chapters = {}
chapter_to_file = {}
renames_needed = []

for i in range(0, 361):
    fname = f"ch{i:03d}.md"
    fpath = os.path.join(chapter_dir, fname)
    if not os.path.exists(fpath):
        missing_files.append(i)
        continue
    with open(fpath, 'r') as f:
        first_line = f.readline().strip()
    title_num = extract_chapter_num(first_line)
    if title_num is None:
        issues.append((i, fname, "无法提取章节号", first_line[:40]))
        continue
    if title_num < 0 or title_num > 360:
        issues.append((i, fname, f"章节号异常({title_num})", first_line[:40]))
        continue
    if title_num in chapter_to_file:
        if title_num not in duplicate_chapters:
            duplicate_chapters[title_num] = []
        duplicate_chapters[title_num].append((i, fname, first_line[:50]))
    else:
        chapter_to_file[title_num] = (i, fname, first_line[:50])
    covered_chapters.add(title_num)

    # 检查是否需要重命名
    if i >= 1 and i <= 360 and title_num != i:
        new_fname = f"ch{title_num:03d}.md"
        # 检查目标文件是否已存在
        target_exists = os.path.exists(os.path.join(chapter_dir, new_fname))
        renames_needed.append((i, fname, title_num, new_fname, target_exists, first_line[:40]))

# 检查缺失章节（1-360）
full_range = set(range(1, 361))
missing_chapters = sorted(full_range - covered_chapters)

print("=" * 70)
print("校验结果汇总")
print("=" * 70)
print(f"总文件数: 360")
print(f"文件缺失: {len(missing_files)} 个 - {missing_files}")
print(f"命名问题: {len(issues)} 个")
print(f"章节覆盖: {len(covered_chapters)} 章（1-360范围内）")
print(f"内容缺失章节号: {len(missing_chapters)} 个")
print(f"重复章节号: {len(duplicate_chapters)} 个")
print(f"需重命名: {len(renames_needed)} 个")

if duplicate_chapters:
    print("\n" + "=" * 70)
    print("重复章节号详情")
    print("=" * 70)
    for cn, files in sorted(duplicate_chapters.items()):
        print(f"\n章节{cn}:")
        for i, fname, line in files:
            print(f"  ch{i:03d}: {line}")

if issues:
    print("\n" + "=" * 70)
    print("无法提取章节号的问题文件")
    print("=" * 70)
    for i, fname, issue, line in issues:
        print(f"ch{i:03d}: {issue} - {line}")

if renames_needed:
    print("\n" + "=" * 70)
    print("需要重命名的文件")
    print("=" * 70)
    conflict_renames = [r for r in renames_needed if r[4]]  # target exists
    simple_renames = [r for r in renames_needed if not r[4]]  # target doesn't exist

    print(f"\n简单重命名（目标文件不存在）: {len(simple_renames)} 个")
    for old_num, old_fname, title_num, new_fname, target_exists, line in simple_renames[:10]:
        print(f"  {old_fname} -> {new_fname}")
        print(f"    标题: {line[:40]}")
    if len(simple_renames) > 10:
        print(f"  ... 还有 {len(simple_renames) - 10} 个")

    if conflict_renames:
        print(f"\n冲突重命名（目标文件已存在）: {len(conflict_renames)} 个")
        for old_num, old_fname, title_num, new_fname, target_exists, line in conflict_renames:
            print(f"  {old_fname} -> {new_fname} (冲突!)")
            print(f"    标题: {line[:40]}")

print("\n" + "=" * 70)
print("缺失章节内容分析")
print("=" * 70)
for m in missing_chapters[:10]:
    # 找相邻章节
    prev_ch = m - 1 if m > 1 else None
    next_ch = m + 1 if m < 360 else None
    prev_info = chapter_to_file.get(prev_ch, (str(prev_ch), str(prev_ch), "无")) if prev_ch else (str(prev_ch), str(prev_ch), "无")
    next_info = chapter_to_file.get(next_ch, (str(next_ch), str(next_ch), "无")) if next_ch else (str(next_ch), str(next_ch), "无")
    print(f"章节{m}缺失:")
    print(f"  前一章: {prev_info[0]} - {prev_info[2][:30]}")
    print(f"  后一章: {next_info[0]} - {next_info[2][:30]}")

PYTHON_SCRIPT

echo ""
echo -e "${BLUE}=== 校验完成 ===${NC}"
echo ""
echo "如需生成修复脚本，请运行:"
echo "  ./run_publish.sh fix_naming --dry-run  # 预览"
echo "  ./run_publish.sh fix_naming            # 执行修复"