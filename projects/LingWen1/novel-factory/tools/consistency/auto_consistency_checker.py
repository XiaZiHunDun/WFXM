#!/usr/bin/env python3
"""
自动化一致性检查器 - 主控调度
作为守门员在以下时机运行：
1. 章节创作完成后（进入意见仓库前）
2. 批量审核前（作为预检）
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# 导入各检查器
from check_naming import check_naming, report_naming_issues
from check_content_integrity import check_integrity, report_integrity_issues
from check_duplicate import check_chapter_duplicates, report_duplicate_issues
from check_character_state import check_character_consistency, report_character_issues, CHARACTER_TRACKER
from check_timeline import check_timeline_anomalies, report_timeline_issues


class ConsistencyChecker:
    """一致性检查器主控"""

    def __init__(self, chapters_dir: str, output_dir: str = None):
        self.chapters_dir = chapters_dir
        self.output_dir = output_dir
        self.issues: List[Tuple] = []
        self.report_sections = []

    def run_all_checks(self, chapter_range: tuple[int, int] = (1, 360),
                       skip_duplicates: bool = False,
                       min_word_count: int = 500,
                       duplicate_threshold: float = 0.8,
                       characters: List[str] = None) -> Dict:
        """
        运行所有检查项

        Args:
            chapter_range: 检查章节范围
            skip_duplicates: 是否跳过重复检测（O(n^2)较慢）
            min_word_count: 最低字数
            duplicate_threshold: 重复检测阈值
            characters: 要检查的人物列表

        Returns:
            dict with check results
        """
        start_time = datetime.now()
        results = {
            'started_at': start_time.isoformat(),
            'chapter_range': f"{chapter_range[0]}-{chapter_range[1]}",
            'checks': {},
            'total_issues': 0,
            'by_severity': {'P0': 0, 'P1': 0, 'P2': 0},
        }

        print("=" * 70)
        print("自动化一致性检查")
        print("=" * 70)
        print(f"章节范围: ch{chapter_range[0]:03d}-ch{chapter_range[1]:03d}")
        print(f"检查时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # 1. 命名一致性检查
        print("▶ 命名一致性检查...")
        naming_issues = check_naming(self.chapters_dir, chapter_range)
        self.issues.extend(naming_issues)
        results['checks']['naming'] = {
            'issues': len(naming_issues),
            'details': naming_issues[:50],  # 限制数量
        }
        for issue in naming_issues:
            results['by_severity']['P0'] += 1
        print(f"  发现问题: {len(naming_issues)} 个")

        # 2. 内容完整性检查
        print("▶ 内容完整性检查...")
        integrity_issues = check_integrity(self.chapters_dir, chapter_range, min_word_count)
        self.issues.extend(integrity_issues)
        results['checks']['integrity'] = {
            'issues': len(integrity_issues),
            'details': integrity_issues[:50],
        }
        for issue in integrity_issues:
            results['by_severity']['P0'] += 1  # 空章节/无结尾标记是P0
        print(f"  发现问题: {len(integrity_issues)} 个")

        # 3. 重复内容检测（可选，耗时较长）
        if skip_duplicates:
            print("▶ [跳过] 重复内容检测")
            results['checks']['duplicates'] = {'issues': 0, 'skipped': True}
        else:
            print("▶ 重复内容检测（可能耗时较长）...")
            duplicate_issues = check_chapter_duplicates(
                self.chapters_dir, chapter_range, duplicate_threshold
            )
            self.issues.extend(duplicate_issues)
            results['checks']['duplicates'] = {
                'issues': len(duplicate_issues),
                'details': duplicate_issues[:50],
            }
            for issue in duplicate_issues:
                results['by_severity']['P0'] += 1
            print(f"  发现问题: {len(duplicate_issues)} 对")

        # 4. 人物状态追踪
        print("▶ 人物状态追踪...")
        char_issues = check_character_consistency(
            self.chapters_dir, chapter_range, characters
        )
        self.issues.extend(char_issues)
        results['checks']['character'] = {
            'issues': len(char_issues),
            'details': char_issues[:50],
        }
        for issue in char_issues:
            results['by_severity']['P1'] += 1  # 人物状态问题通常是P1
        print(f"  发现问题: {len(char_issues)} 处")

        # 5. 时间线校验
        print("▶ 时间线校验...")
        timeline_issues = check_timeline_anomalies(self.chapters_dir, chapter_range)
        self.issues.extend(timeline_issues)
        results['checks']['timeline'] = {
            'issues': len(timeline_issues),
            'details': timeline_issues[:50],
        }
        for issue in timeline_issues:
            results['by_severity']['P2'] += 1  # 时间线问题通常是P2
        print(f"  发现问题: {len(timeline_issues)} 处")

        end_time = datetime.now()
        results['completed_at'] = end_time.isoformat()
        results['duration_seconds'] = (end_time - start_time).total_seconds()
        results['total_issues'] = len(self.issues)

        return results

    def generate_report(self, results: Dict, format: str = 'markdown') -> str:
        """生成统一检查报告"""
        lines = []

        if format == 'markdown':
            lines.append("# 自动化一致性检查报告")
            lines.append("")
            lines.append(f"**检查时间**: {results['started_at']}")
            lines.append(f"**完成时间**: {results['completed_at']}")
            lines.append(f"**耗时**: {results['duration_seconds']:.2f}秒")
            lines.append(f"**章节范围**: {results['chapter_range']}")
            lines.append("")
            lines.append(f"**问题统计**: {results['total_issues']} 个")
            lines.append(f"- P0 (严重): {results['by_severity']['P0']} 个")
            lines.append(f"- P1 (高优): {results['by_severity']['P1']} 个")
            lines.append(f"- P2 (中优): {results['by_severity']['P2']} 个")
            lines.append("")

            lines.append("## 检查详情")
            lines.append("")

            # 命名检查
            naming = results['checks'].get('naming', {})
            lines.append(f"### 命名一致性: {naming.get('issues', 0)} 个问题")
            if naming.get('issues', 0) > 0 and naming.get('details'):
                for issue in naming['details'][:10]:
                    lines.append(f"- ch{issue[1]:03d}.md: {issue[3]}")
            lines.append("")

            # 内容完整性
            integrity = results['checks'].get('integrity', {})
            lines.append(f"### 内容完整性: {integrity.get('issues', 0)} 个问题")
            if integrity.get('issues', 0) > 0 and integrity.get('details'):
                by_type = {}
                for issue in integrity['details']:
                    t = issue[0]
                    if t not in by_type:
                        by_type[t] = []
                    by_type[t].append(issue)
                for t, items in by_type.items():
                    lines.append(f"- {t}: {len(items)} 个")
            lines.append("")

            # 重复内容
            duplicates = results['checks'].get('duplicates', {})
            if duplicates.get('skipped'):
                lines.append("### 重复内容检测: 已跳过")
            else:
                lines.append(f"### 重复内容: {duplicates.get('issues', 0)} 对问题")
                if duplicates.get('issues', 0) > 0 and duplicates.get('details'):
                    for issue in duplicates['details'][:5]:
                        lines.append(f"- {issue[3]}")
            lines.append("")

            # 人物状态
            character = results['checks'].get('character', {})
            lines.append(f"### 人物状态: {character.get('issues', 0)} 处问题")
            if character.get('issues', 0) > 0 and character.get('details'):
                by_char = {}
                for issue in character['details']:
                    c = issue[2]
                    if c not in by_char:
                        by_char[c] = []
                    by_char[c].append(issue)
                for c, items in by_char.items():
                    lines.append(f"- {c}: {len(items)} 处")
            lines.append("")

            # 时间线
            timeline = results['checks'].get('timeline', {})
            lines.append(f"### 时间线: {timeline.get('issues', 0)} 处问题")
            if timeline.get('issues', 0) > 0 and timeline.get('details'):
                for issue in timeline['details'][:5]:
                    lines.append(f"- ch{issue[1]:03d}: {issue[2]}")
            lines.append("")

            # 判定结论
            lines.append("## 判定结论")
            lines.append("")
            if results['total_issues'] == 0:
                lines.append("✅ **通过** - 未发现一致性问题")
            elif results['by_severity']['P0'] > 0:
                lines.append(f"❌ **不通过** - 发现 {results['by_severity']['P0']} 个P0问题，需修复后重新检查")
            elif results['by_severity']['P1'] > 0:
                lines.append(f"⚠️ **有条件通过** - 发现 {results['by_severity']['P1']} 个P1问题，建议修复")
            else:
                lines.append(f"✅ **通过** - 仅发现 {results['by_severity']['P2']} 个P2问题，可接受")

        return "\n".join(lines)

    def save_report(self, results: Dict, report_path: str = None):
        """保存报告到文件"""
        if not report_path:
            if self.output_dir:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                report_path = os.path.join(self.output_dir, f"consistency_check_{timestamp}.md")
            else:
                report_path = "consistency_check_report.md"

        # 确保目录存在
        os.makedirs(os.path.dirname(report_path) if os.path.dirname(report_path) else '.', exist_ok=True)

        report = self.generate_report(results)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        # 同时保存JSON格式的详细结果
        json_path = report_path.replace('.md', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return report_path, json_path


def main():
    parser = argparse.ArgumentParser(description='自动化一致性检查器')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--output', '-o', help='输出报告目录')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=360, help='结束章节')
    parser.add_argument('--skip-duplicates', action='store_true', help='跳过重复检测')
    parser.add_argument('--min-word-count', type=int, default=500, help='最低字数')
    parser.add_argument('--duplicate-threshold', type=float, default=0.8, help='重复检测阈值')
    parser.add_argument('--characters', nargs='+', help='指定检查的人物')
    parser.add_argument('--report', '-r', help='报告输出路径')
    args = parser.parse_args()

    checker = ConsistencyChecker(args.chapters_dir, args.output)

    results = checker.run_all_checks(
        chapter_range=(args.start, args.end),
        skip_duplicates=args.skip_duplicates,
        min_word_count=args.min_word_count,
        duplicate_threshold=args.duplicate_threshold,
        characters=args.characters,
    )

    report_path, json_path = checker.save_report(results, args.report)

    print()
    print("=" * 70)
    print("检查完成")
    print("=" * 70)
    print(f"报告: {report_path}")
    print(f"详细JSON: {json_path}")
    print(f"总问题数: {results['total_issues']}")
    print(f"  P0: {results['by_severity']['P0']}")
    print(f"  P1: {results['by_severity']['P1']}")
    print(f"  P2: {results['by_severity']['P2']}")

    # 返回码：有问题则失败
    sys.exit(0 if results['total_issues'] == 0 else 1)


if __name__ == "__main__":
    main()