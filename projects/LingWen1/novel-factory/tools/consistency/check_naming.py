#!/usr/bin/env python3
"""
章节命名一致性检查器
检测文件名与内容章节号是否匹配
"""
import re
import os
import sys
from pathlib import Path

# 中文数字转换
ZH_DIGIT_MAP = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def chinese_to_arabic(zh: str) -> int | None:
    """中文数字转阿拉伯数字（正确处理"三十一"等复合数字）"""
    if zh == '零':
        return 0

    if zh == '十':
        return 10

    if '百' in zh:
        parts = zh.split('百', 1)
        hundred_part = parts[0] if parts[0] else '一'
        rest = parts[1] if len(parts) > 1 else ''
        hundred_val = ZH_DIGIT_MAP.get(hundred_part, 1) * 100

        if not rest:
            return hundred_val

        rest_val = chinese_to_arabic(rest)
        return hundred_val + (rest_val if rest_val is not None else 0)

    result = 0
    temp_num = 0
    i = 0
    while i < len(zh):
        char = zh[i]
        if char == '十':
            if temp_num == 0:
                result = 10
            else:
                result = temp_num * 10
                temp_num = 0
        elif char in ZH_DIGIT_MAP:
            temp_num = temp_num * 10 + ZH_DIGIT_MAP[char]
        else:
            return None
        i += 1

    result += temp_num
    return result if result > 0 else None


def extract_chapter_num(title: str) -> int | None:
    """从标题提取章节号"""
    match = re.search(r'第([零一二三四五六七八九十百]+)章', title)
    if not match:
        return None
    zh = match.group(1)
    return chinese_to_arabic(zh)


def check_naming(chapters_dir: str, chapter_range: tuple[int, int] = (1, 360)) -> list[tuple]:
    """
    检查章节命名一致性

    Returns:
        list of (issue_type, chapter_num, file_name, message) tuples
    """
    issues = []
    start, end = chapter_range

    for i in range(start, end + 1):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapters_dir, fname)

        if not os.path.exists(fpath):
            issues.append(("MISSING_FILE", i, fname, f"文件缺失"))
            continue

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
        except Exception as e:
            issues.append(("READ_ERROR", i, fname, f"读取失败: {e}"))
            continue

        title_num = extract_chapter_num(first_line)
        if title_num is None:
            issues.append(("NO_CHAPTER_NUM", i, fname, f"无法提取章节号: {first_line[:40]}"))
            continue

        if title_num < 0 or title_num > 360:
            issues.append(("INVALID_CHAPTER_NUM", i, fname, f"章节号异常({title_num})"))
            continue

        # 检查文件名与章节号是否匹配
        if title_num != i:
            issues.append(("MISMATCH", i, fname,
                f"文件名ch{i:03d}对应内容第{title_num}章"))

    return issues


def report_naming_issues(issues: list[tuple], output_file: str = None) -> str:
    """生成命名检查报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("章节命名一致性检查报告")
    lines.append("=" * 70)

    if not issues:
        lines.append("\n✅ 所有章节命名一致")
        report = "\n".join(lines)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        return report

    # 按问题类型分组
    by_type = {}
    for issue in issues:
        issue_type = issue[0]
        if issue_type not in by_type:
            by_type[issue_type] = []
        by_type[issue_type].append(issue)

    lines.append(f"\n发现问题: {len(issues)} 个")

    for issue_type, items in by_type.items():
        lines.append(f"\n--- {issue_type} ({len(items)}个) ---")
        for item in items[:20]:  # 最多显示20个
            lines.append(f"  {item[1]:03d}.md - {item[3]}")
        if len(items) > 20:
            lines.append(f"  ... 还有 {len(items) - 20} 个")

    report = "\n".join(lines)
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='章节命名一致性检查')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--output', '-o', help='输出报告路径')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=360, help='结束章节')
    args = parser.parse_args()

    issues = check_naming(args.chapters_dir, (args.start, args.end))
    report = report_naming_issues(issues, args.output)
    print(report)

    sys.exit(0 if not issues else 1)