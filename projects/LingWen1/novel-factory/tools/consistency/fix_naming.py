#!/usr/bin/env python3
"""
自动修复章节命名问题
将文件名重命名为内容中的实际章节号
"""
import os
import sys
import re
from pathlib import Path

ZH_DIGIT_MAP = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def extract_chapter_num(title: str) -> int | None:
    """从标题提取章节号"""
    match = re.search(r'第([零一二三四五六七八九十百]+)章', title)
    if not match:
        return None
    zh = match.group(1)

    return chinese_to_arabic(zh)


def chinese_to_arabic(zh: str) -> int | None:
    """中文数字转阿拉伯数字（正确处理"三十一"等复合数字）"""
    if zh == '零':
        return 0

    # 特殊处理"十"
    if zh == '十':
        return 10

    # 预处理：去掉"第"字后面可能有的计量单位前缀（如果有的话）
    # 但这里zh已经是提取出来的，所以直接处理

    # 检查是否有"百"及以上
    if '百' in zh:
        parts = zh.split('百', 1)
        hundred_part = parts[0] if parts[0] else '一'
        rest = parts[1] if len(parts) > 1 else ''
        hundred_val = ZH_DIGIT_MAP.get(hundred_part, 1) * 100

        if not rest:
            return hundred_val

        # 递归处理rest（不包含百的部分）
        rest_val = chinese_to_arabic(rest)
        return hundred_val + (rest_val if rest_val is not None else 0)

    # 处理纯十进制数字（十~九十九，不含百）
    # 算法：从左到右，遇到"十"时特殊处理
    result = 0
    temp_num = 0

    i = 0
    while i < len(zh):
        char = zh[i]

        if char == '十':
            # 十有特殊含义：
            # - 如果temp_num为0，说明这是"十三"之类的"十开头"
            # - 如果temp_num非0，说明这是"三十"之类的"几十"
            if temp_num == 0:
                # "十三" = 10 + 3
                result = 10
            else:
                # "三十" = 30
                result = temp_num * 10
                temp_num = 0
        elif char in ZH_DIGIT_MAP:
            temp_num = temp_num * 10 + ZH_DIGIT_MAP[char]
        else:
            # 未知字符
            return None
        i += 1

    # 加上最后累积的temp_num（如"三十一"中的"一"）
    result += temp_num

    return result if result > 0 else None


def scan_and_fix_naming(chapters_dir: str, dry_run: bool = True) -> dict:
    """
    扫描并修复命名问题

    Args:
        chapters_dir: 章节目录
        dry_run: True=只报告不执行，False=实际重命名

    Returns:
        dict with fix results
    """
    results = {
        'dry_run': dry_run,
        'total_files': 0,
        'needs_rename': [],
        'already_correct': [],
        'errors': [],
        'conflicts': [],
    }

    for i in range(0, 361):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapters_dir, fname)

        if not os.path.exists(fpath):
            continue

        results['total_files'] += 1

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
        except Exception as e:
            results['errors'].append((fname, f"读取失败: {e}"))
            continue

        title_num = extract_chapter_num(first_line)
        if title_num is None or title_num < 1 or title_num > 360:
            results['errors'].append((fname, f"无法提取有效章节号: {first_line[:40]}"))
            continue

        # 检查是否需要重命名
        if title_num != i:
            target_fname = f"ch{title_num:03d}.md"
            target_exists = os.path.exists(os.path.join(chapters_dir, target_fname))

            entry = {
                'current': fname,
                'target': target_fname,
                'content_num': title_num,
                'title': first_line[:50],
                'target_exists': target_exists,
            }

            if target_exists:
                results['conflicts'].append(entry)
            else:
                results['needs_rename'].append(entry)

            if not dry_run:
                try:
                    os.rename(fpath, os.path.join(chapters_dir, target_fname))
                    entry['renamed'] = True
                except Exception as e:
                    entry['error'] = str(e)
        else:
            results['already_correct'].append(fname)

    return results


def print_results(results: dict):
    """打印修复结果"""
    print("=" * 70)
    print("章节命名修复报告")
    print("=" * 70)
    print(f"总文件数: {results['total_files']}")
    print(f"无需修改: {len(results['already_correct'])} 个")
    print(f"需重命名: {len(results['needs_rename'])} 个")
    print(f"冲突(目标已存在): {len(results['conflicts'])} 个")
    print(f"错误: {len(results['errors'])} 个")

    if results['dry_run']:
        print("\n⚠️  DRY RUN - 未实际执行重命名")

    if results['needs_rename']:
        print("\n--- 需要重命名的文件 ---")
        for item in results['needs_rename'][:20]:
            status = "✅" if not results['dry_run'] and item.get('renamed') else "→"
            print(f"  {status} {item['current']} → {item['target']}")
            print(f"      内容: {item['title']}")
        if len(results['needs_rename']) > 20:
            print(f"  ... 还有 {len(results['needs_rename']) - 20} 个")

    if results['conflicts']:
        print("\n--- 冲突（目标文件已存在）---")
        for item in results['conflicts']:
            print(f"  ⚠️  {item['current']} 应改为 {item['target']}，但目标已存在")
            print(f"      内容: {item['title']}")

    if results['errors']:
        print("\n--- 错误 ---")
        for fname, msg in results['errors']:
            print(f"  ❌ {fname}: {msg}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='自动修复章节命名问题')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--execute', action='store_true', help='实际执行重命名（默认dry-run）')
    parser.add_argument('--report', help='保存报告到文件')
    args = parser.parse_args()

    results = scan_and_fix_naming(args.chapters_dir, dry_run=not args.execute)
    print_results(results)

    if args.report:
        import json
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {args.report}")

    if not args.execute:
        print("\n💡 如需实际执行重命名，请添加 --execute 参数")

    # 返回码：有冲突或需重命名则失败
    has_issues = len(results['needs_rename']) > 0 or len(results['conflicts']) > 0
    sys.exit(0 if not has_issues else 1)


if __name__ == "__main__":
    main()