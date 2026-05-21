#!/usr/bin/env python3
"""
章节内容完整性检查器
检测：结尾标记、字数下限、空章节
"""
import os
import re
import sys


def check_integrity(chapters_dir: str, chapter_range: tuple[int, int] = (1, 360),
                    min_word_count: int = 500) -> list[tuple]:
    """
    检查章节内容完整性

    Args:
        chapters_dir: 章节目录
        chapter_range: 检查章节范围
        min_word_count: 最低字数要求

    Returns:
        list of (issue_type, chapter_num, file_name, message) tuples
    """
    issues = []
    start, end = chapter_range

    for i in range(start, end + 1):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapters_dir, fname)

        if not os.path.exists(fpath):
            issues.append(("MISSING_FILE", i, fname, "文件缺失"))
            continue

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            issues.append(("READ_ERROR", i, fname, f"读取失败: {e}"))
            continue

        char_count = len(content)

        # 检查空文件
        if char_count < 100:
            issues.append(("EMPTY_CHAPTER", i, fname,
                f"章节内容过少({char_count}字符)"))
            continue

        # 检查"本章完"标记
        if "**本章完**" not in content and "【本章完】" not in content:
            issues.append(("MISSING_END_MARK", i, fname, "缺少**本章完**标记"))

        # 检查字数下限
        if char_count < min_word_count:
            issues.append(("LOW_WORD_COUNT", i, fname,
                f"字数{char_count}低于{min_word_count}"))

    return issues


def report_integrity_issues(issues: list[tuple], output_file: str = None) -> str:
    """生成完整性检查报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("章节内容完整性检查报告")
    lines.append("=" * 70)

    if not issues:
        lines.append("\n✅ 所有章节内容完整")
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
        for item in items[:20]:
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
    parser = argparse.ArgumentParser(description='章节内容完整性检查')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--output', '-o', help='输出报告路径')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=360, help='结束章节')
    parser.add_argument('--min-count', type=int, default=500, help='最低字数')
    args = parser.parse_args()

    issues = check_integrity(args.chapters_dir, (args.start, args.end), args.min_count)
    report = report_integrity_issues(issues, args.output)
    print(report)

    sys.exit(0 if not issues else 1)