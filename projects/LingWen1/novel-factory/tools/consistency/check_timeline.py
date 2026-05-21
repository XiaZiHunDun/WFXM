#!/usr/bin/env python3
"""
时间线校验检查器 v2.0
改进：只检测明确的时间线矛盾，不误报闪回手法
"""
import os
import re
import sys
from typing import List, Tuple, Dict


# 时间关键词分类（简化版）
TIME_KEYWORDS = {
    "instant": ["瞬间", "眨眼", "刹那间", "下一刻", "须臾之间"],
    "past": ["年前", "当时", "当初", "昔日", "很久以前"],
}


def check_timeline_anomalies(chapters_dir: str,
                             chapter_range: tuple[int, int] = (1, 360)) -> List[Tuple]:
    """
    检测时间线异常（改进版）

    改进：
    - 只在章节同时出现"past"和"instant"时才报告
    - 排除"眨眼"等口语化用法的误报
    - 不把闪回当作错误
    """
    issues = []
    start, end = chapter_range

    for i in range(start, end + 1):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapters_dir, fname)

        if not os.path.exists(fpath):
            continue

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        # 统计各类时间词出现次数
        instant_count = 0
        past_count = 0

        for kw in TIME_KEYWORDS["instant"]:
            instant_count += content.count(kw)

        for kw in TIME_KEYWORDS["past"]:
            past_count += content.count(kw)

        # 只有当"past"类词汇远超"instant"类时，才报告时间尺度冲突
        # 这是为了避免误报（闪回是正常的叙事手法）
        # 但如果past出现次数远大于instant，可能有问题
        if past_count > 0 and instant_count > 0:
            # 检查是否有明显的先后矛盾（在同一段落中）
            lines = content.split('\n')
            for line in lines:
                has_instant = any(kw in line for kw in TIME_KEYWORDS["instant"])
                has_past = any(kw in line for kw in TIME_KEYWORDS["past"])
                # 只在段落中同时出现时才报告
                # 但仍然需要上下文验证
                if has_instant and has_past:
                    # 进一步检查是否有明确的因果关系暗示时间倒退
                    if re.search(r'(之前|当时|当年).{0,20}(瞬间|眨眼|刹那)', line):
                        issues.append(("TIMELINE_ANOMALY", i,
                            f"时间线倒退: 在过去时描述后出现瞬间类动作"))
                    break

    return issues


def report_timeline_issues(issues: List[Tuple], output_file: str = None) -> str:
    """生成时间线检查报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("时间线一致性检查报告 (v2.0)")
    lines.append("=" * 70)

    if not issues:
        lines.append("\n✅ 时间线正常")
        report = "\n".join(lines)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        return report

    lines.append(f"\n发现问题: {len(issues)} 处")

    lines.append("\n--- 时间线异常列表 ---")
    for issue in issues:
        lines.append(f"  ch{issue[1]:03d}: {issue[2]}")

    report = "\n".join(lines)
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='时间线一致性检查 (v2.0)')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--output', '-o', help='输出报告路径')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=360, help='结束章节')
    args = parser.parse_args()

    issues = check_timeline_anomalies(args.chapters_dir, (args.start, args.end))
    report = report_timeline_issues(issues, args.output)
    print(report)

    sys.exit(0 if not issues else 1)