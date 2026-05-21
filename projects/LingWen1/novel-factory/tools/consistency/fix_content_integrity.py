#!/usr/bin/env python3
"""
自动修复章节内容完整性问题
- 补充缺失的**本章完**标记
- 报告字数不足的章节（需人工处理）
"""
import os
import re
import sys


def check_and_fix_integrity(chapters_dir: str, dry_run: bool = True,
                             min_word_count: int = 500) -> dict:
    """
    检查并修复内容完整性问题

    Args:
        chapters_dir: 章节目录
        dry_run: True=只报告不执行，False=实际修复
        min_word_count: 最低字数要求

    Returns:
        dict with fix results
    """
    results = {
        'dry_run': dry_run,
        'total_files': 0,
        'fixed_missing_end_mark': [],
        'report_low_word_count': [],
        'already_complete': [],
        'errors': [],
    }

    for i in range(0, 361):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapters_dir, fname)

        if not os.path.exists(fpath):
            continue

        results['total_files'] += 1

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            results['errors'].append((fname, f"读取失败: {e}"))
            continue

        char_count = len(content)
        issues = []

        # 检查字数
        if char_count < min_word_count:
            issues.append(('LOW_WORD_COUNT', char_count))

        # 检查"本章完"标记
        has_end_mark = '**本章完**' in content or '【本章完】' in content

        if issues or not has_end_mark:
            if not has_end_mark:
                if char_count >= min_word_count:
                    # 字数够，可以自动补充标记
                    if not dry_run:
                        # 在文件末尾添加标记
                        with open(fpath, 'w', encoding='utf-8') as f:
                            f.write(content.rstrip() + '\n\n**本章完**\n')
                    results['fixed_missing_end_mark'].append({
                        'file': fname,
                        'char_count': char_count,
                        'action': 'added' if not dry_run else 'would_add'
                    })
                else:
                    # 字数不够，无法自动修复
                    results['report_low_word_count'].append({
                        'file': fname,
                        'char_count': char_count,
                        'missing': min_word_count - char_count
                    })
        else:
            results['already_complete'].append(fname)

    return results


def print_results(results: dict):
    """打印修复结果"""
    print("=" * 70)
    print("章节内容完整性修复报告")
    print("=" * 70)
    print(f"总文件数: {results['total_files']}")
    print(f"内容完整: {len(results['already_complete'])} 个")
    print(f"已补充标记: {len(results['fixed_missing_end_mark'])} 个")
    print(f"字数不足（需人工）: {len(results['report_low_word_count'])} 个")
    print(f"错误: {len(results['errors'])} 个")

    if results['dry_run']:
        print("\n⚠️  DRY RUN - 未实际执行修复")

    if results['fixed_missing_end_mark']:
        print("\n--- 将补充 **本章完** 标记 ---")
        for item in results['fixed_missing_end_mark'][:15]:
            action = "✅" if item['action'] == 'added' else "→"
            print(f"  {action} {item['file']} (字数: {item['char_count']})")
        if len(results['fixed_missing_end_mark']) > 15:
            print(f"  ... 还有 {len(results['fixed_missing_end_mark']) - 15} 个")

    if results['report_low_word_count']:
        print("\n--- 字数不足（需人工处理）---")
        for item in results['report_low_word_count']:
            print(f"  ❌ {item['file']}: {item['char_count']}字 (缺{item['missing']}字)")

    if results['errors']:
        print("\n--- 错误 ---")
        for fname, msg in results['errors']:
            print(f"  ❌ {fname}: {msg}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='自动修复章节内容完整性问题')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--execute', action='store_true', help='实际执行修复（默认dry-run）')
    parser.add_argument('--min-count', type=int, default=500, help='最低字数要求')
    parser.add_argument('--report', help='保存报告到文件')
    args = parser.parse_args()

    results = check_and_fix_integrity(
        args.chapters_dir,
        dry_run=not args.execute,
        min_word_count=args.min_count
    )
    print_results(results)

    if args.report:
        import json
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {args.report}")

    if not args.execute:
        print("\n💡 如需实际执行修复，请添加 --execute 参数")

    # 字数不足需要人工，返回非零
    has_issues = len(results['report_low_word_count']) > 0
    sys.exit(0 if not has_issues else 1)


if __name__ == "__main__":
    main()