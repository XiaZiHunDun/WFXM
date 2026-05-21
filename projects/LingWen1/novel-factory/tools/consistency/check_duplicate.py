#!/usr/bin/env python3
"""
章节重复内容检测器
使用文本相似度检测跨章节重复内容
"""
import os
import sys
from difflib import SequenceMatcher
from typing import List, Tuple, Dict


def calculate_similarity(text1: str, text2: str) -> float:
    """计算两段文本的相似度"""
    # 移除多余空白进行比对
    t1 = ' '.join(text1.split())
    t2 = ' '.join(text2.split())
    return SequenceMatcher(None, t1, t2).ratio()


def load_chapter(fpath: str) -> str:
    """加载章节内容"""
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""


def load_all_chapters(chapters_dir: str, chapter_range: tuple[int, int] = (1, 360)) -> List[Dict]:
    """加载所有章节"""
    chapters = []
    start, end = chapter_range

    for i in range(start, end + 1):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapters_dir, fname)

        if os.path.exists(fpath):
            content = load_chapter(fpath)
            chapters.append({
                'num': i,
                'filename': fname,
                'path': fpath,
                'content': content
            })

    return chapters


def check_chapter_duplicates(chapters_dir: str,
                             chapter_range: tuple[int, int] = (1, 360),
                             threshold: float = 0.8) -> List[Tuple]:
    """
    检测章节间重复内容

    Args:
        chapters_dir: 章节目录
        chapter_range: 检查章节范围
        threshold: 相似度阈值（超过此值则预警）

    Returns:
        list of (issue_type, chapter1, chapter2, message) tuples
    """
    issues = []
    chapters = load_all_chapters(chapters_dir, chapter_range)

    n = len(chapters)
    checked = 0

    for i in range(n):
        for j in range(i + 1, n):
            ch1 = chapters[i]
            ch2 = chapters[j]

            similarity = calculate_similarity(ch1['content'], ch2['content'])

            if similarity > threshold:
                issues.append(("DUPLICATE_CONTENT",
                    ch1['num'], ch2['num'],
                    f"ch{ch1['num']:03d}与ch{ch2['num']:03d}相似度{similarity:.2%}"))

            checked += 1

    return issues


def report_duplicate_issues(issues: List[Tuple], output_file: str = None) -> str:
    """生成重复内容检测报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("章节重复内容检测报告")
    lines.append("=" * 70)

    if not issues:
        lines.append("\n✅ 未检测到重复内容")
        report = "\n".join(lines)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        return report

    lines.append(f"\n发现重复内容: {len(issues)} 对")

    # 按相似度排序
    issues_sorted = sorted(issues, key=lambda x: float(x[3].split('相似度')[1].replace('%', '')) / 100, reverse=True)

    lines.append("\n--- 重复内容列表 ---")
    for issue in issues_sorted:
        lines.append(f"  {issue[3]}")

    report = "\n".join(lines)
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='章节重复内容检测')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--output', '-o', help='输出报告路径')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=360, help='结束章节')
    parser.add_argument('--threshold', type=float, default=0.8, help='相似度阈值(0-1)')
    args = parser.parse_args()

    issues = check_chapter_duplicates(args.chapters_dir, (args.start, args.end), args.threshold)
    report = report_duplicate_issues(issues, args.output)
    print(report)

    sys.exit(0 if not issues else 1)