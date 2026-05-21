#!/bin/bash
#===============================================================================
# 章节文件命名修复脚本 v2.0
# 用途：自动修复文件命名与章节标题不一致的问题
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

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo -e "${YELLOW}[dry-run 模式] 仅预览，不实际修改文件${NC}"
    echo ""
fi

# 使用Python分析并生成修复方案
python3 << 'PYTHON_SCRIPT'
import re
import os
import shutil

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

# 建立当前文件映射：文件名 -> (标题章节号, 实际标题)
file_info = {}  # file_num -> (title_num, first_line)
title_to_files = {}  # title_num -> [(file_num, first_line), ...]

for i in range(0, 361):
    fname = f"ch{i:03d}.md"
    fpath = os.path.join(chapter_dir, fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath, 'r') as f:
        first_line = f.readline().strip()
    title_num = extract_chapter_num(first_line)
    if title_num is None:
        continue
    file_info[i] = (title_num, first_line)
    if title_num not in title_to_files:
        title_to_files[title_num] = []
    title_to_files[title_num].append((i, first_line))

# 分析需要修复的文件对
# 规则：如果 file_num != title_num，则需要重命名
fixes_needed = []
for file_num, (title_num, line) in file_info.items():
    if file_num >= 1 and file_num <= 360 and title_num >= 1 and title_num <= 360:
        if file_num != title_num:
            fixes_needed.append((file_num, title_num, line))

# 检测冲突（目标文件已存在）
conflicts = []
safe_fixes = []

for old_num, new_num, line in fixes_needed:
    target_path = os.path.join(chapter_dir, f"ch{new_num:03d}.md")
    if os.path.exists(target_path):
        # 检查目标文件是否也应该被移动
        target_info = file_info.get(new_num)
        if target_info:
            target_title_num = target_info[0]
            if target_title_num != new_num:
                # 目标文件也有问题，形成链式冲突
                conflicts.append((old_num, new_num, line, "链式冲突"))
            else:
                conflicts.append((old_num, new_num, line, "目标文件正确"))
        else:
            conflicts.append((old_num, new_num, line, "目标文件无标题"))
    else:
        safe_fixes.append((old_num, new_num, line))

print("=" * 70)
print("章节文件命名修复分析")
print("=" * 70)

print(f"\n安全修复（目标文件不存在）: {len(safe_fixes)} 个")
for old_num, new_num, line in safe_fixes:
    print(f"  ch{old_num:03d}.md -> ch{new_num:03d}.md")
    print(f"    标题: {line[:45]}")

print(f"\n冲突修复（目标文件已存在）: {len(conflicts)} 个")
for old_num, new_num, line, reason in conflicts:
    print(f"  ch{old_num:03d}.md -> ch{new_num:03d}.md ({reason})")
    print(f"    标题: {line[:45]}")

# 检测循环依赖
print("\n" + "=" * 70)
print("循环依赖检测")
print("=" * 70)

# 构建重定向图
graph = {}  # old_num -> new_num
for old_num, new_num, _ in fixes_needed:
    graph[old_num] = new_num

# 检测循环
def find_cycle(node, visited, path):
    if node in visited:
        return None
    if node in path:
        return path[path.index(node):] + [node]
    visited.add(node)
    path.append(node)
    if node in graph:
        return find_cycle(graph[node], visited, path)
    return None

cycles = []
visited_all = set()
for node in graph:
    if node not in visited_all:
        cycle = find_cycle(node, set(), [])
        if cycle:
            cycles.append(cycle)
            visited_all.update(cycle)

if cycles:
    print(f"发现 {len(cycles)} 个循环依赖:")
    for cycle in cycles:
        print(f"  {' -> '.join(f'ch{x:03d}' for x in cycle)}")
else:
    print("无循环依赖")

PYTHON_SCRIPT

echo ""
echo "=" * 70
echo "修复策略"
echo "=" * 70

if [[ "$DRY_RUN" == "true" ]]; then
    echo "dry-run 模式：仅显示修复方案，不执行"
else
    echo "即将执行修复..."
fi

echo ""
echo "修复步骤："
echo "1. 对于无冲突的修复，直接重命名"
echo "2. 对于有冲突的修复，使用临时文件名过渡"
echo ""

if [[ "$DRY_RUN" == "false" ]]; then
    read -p "确认执行修复? (y/n): " confirm
    if [[ "$confirm" != "y" ]]; then
        echo "已取消"
        exit 0
    fi
fi

# 执行修复
python3 << 'PYTHON_EXEC'
import re
import os
import shutil

def extract_chapter_num(title):
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
DRY_RUN = False

# 收集所有修复对
file_info = {}
for i in range(0, 361):
    fname = f"ch{i:03d}.md"
    fpath = os.path.join(chapter_dir, fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath, 'r') as f:
        first_line = f.readline().strip()
    title_num = extract_chapter_num(first_line)
    if title_num is None:
        continue
    file_info[i] = (title_num, first_line)

fixes_needed = []
for file_num, (title_num, line) in file_info.items():
    if file_num >= 1 and file_num <= 360 and title_num >= 1 and title_num <= 360:
        if file_num != title_num:
            fixes_needed.append((file_num, title_num, line))

# 使用临时文件解决冲突
import tempfile
import subprocess

# 创建临时目录
temp_dir = tempfile.mkdtemp(prefix="chapter_fix_")

def safe_rename(src, dst):
    """安全重命名，处理冲突"""
    if not os.path.exists(src):
        print(f"  跳过: {src} 不存在")
        return False
    if os.path.exists(dst) and os.path.getsize(src) == os.path.getsize(dst):
        # 可能已经是正确的文件
        with open(src, 'r') as f:
            src_content = f.read(100)
        with open(dst, 'r') as f:
            dst_content = f.read(100)
        if src_content == dst_content:
            print(f"  相同文件: {src} -> {dst} (跳过)")
            return True
    shutil.move(src, dst)
    return True

print("\n执行修复...")

# 先处理无冲突的
safe_fixes = []
conflicts = []
for old_num, new_num, line in fixes_needed:
    target = os.path.join(chapter_dir, f"ch{new_num:03d}.md")
    if not os.path.exists(target):
        safe_fixes.append((old_num, new_num))
    else:
        conflicts.append((old_num, new_num))

print(f"\n步骤1: 安全修复 ({len(safe_fixes)} 个)")
for old_num, new_num in safe_fixes:
    src = os.path.join(chapter_dir, f"ch{old_num:03d}.md")
    dst = os.path.join(chapter_dir, f"ch{new_num:03d}.md")
    if DRY_RUN:
        print(f"  [dry-run] mv {src} -> {dst}")
    else:
        if safe_rename(src, dst):
            print(f"  mv {old_num:03d} -> {new_num:03d}")

print(f"\n步骤2: 冲突修复 ({len(conflicts)} 个)")
print("  使用临时文件过渡...")

for old_num, new_num in conflicts:
    src = os.path.join(chapter_dir, f"ch{old_num:03d}.md")
    temp_file = os.path.join(temp_dir, f"ch{old_num:03d}.md")
    dst = os.path.join(chapter_dir, f"ch{new_num:03d}.md")

    if DRY_RUN:
        print(f"  [dry-run] mv {src} -> {temp_file} -> {dst}")
        continue

    # 1. 源文件 -> 临时文件
    if os.path.exists(src):
        shutil.move(src, temp_file)
        print(f"  mv {old_num:03d} -> temp")

        # 2. 如果目标存在，先移到temp
        if os.path.exists(dst):
            target_temp = os.path.join(temp_dir, f"ch{new_num:03d}_orig.md")
            shutil.move(dst, target_temp)
            print(f"  mv {new_num:03d} -> temp_backup")

        # 3. 临时文件 -> 目标
        shutil.move(temp_file, dst)
        print(f"  mv temp -> {new_num:03d}")

# 清理临时目录
if not DRY_RUN:
    shutil.rmtree(temp_dir, ignore_errors=True)

print("\n" + "=" * 70)
print("修复完成")
print("=" * 70)

PYTHON_EXEC

# 验证修复结果
echo ""
echo "验证修复结果..."
bash "$SCRIPT_DIR/run_check_naming.sh" | head -30