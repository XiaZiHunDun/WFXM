#!/usr/bin/env python3
"""
章节文件索引更新脚本
用途：自动扫描并更新章节文件的索引数据库

使用方式：
    python3 update_index.py --all      # 更新全部索引
    python3 update_index.py --query ch078  # 查询单个章节
    python3 update_index.py --missing  # 检查缺失章节
    python3 update_index.py --verify   # 验证索引一致性
"""

import re
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# 中文数字转阿拉伯数字
def chinese_to_num(zh: str) -> Optional[int]:
    """中文数字转阿拉伯数字"""
    if zh == '零':
        return 0
    if zh == '十':
        return 10

    digit_map = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                 '六': 6, '七': 7, '八': 8, '九': 9}

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


def extract_chapter_num(title: str) -> Optional[int]:
    """从标题提取章节号"""
    match = re.search(r'第([零一二三四五六七八九十百]+)章', title)
    if not match:
        return None
    return chinese_to_num(match.group(1))


def scan_chapters(chapter_dir: str) -> Dict[int, Dict]:
    """扫描章节目录，返回章节信息字典"""
    chapters = {}

    for i in range(0, 361):
        fname = f"ch{i:03d}.md"
        fpath = os.path.join(chapter_dir, fname)

        if not os.path.exists(fpath):
            continue

        with open(fpath, 'r') as f:
            first_line = f.readline().strip()

        title_num = extract_chapter_num(first_line)
        file_size = os.path.getsize(fpath)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()

        chapters[i] = {
            "file": fname,
            "title": first_line,
            "title_num": title_num,
            "file_num": i,
            "size": file_size,
            "mtime": file_mtime,
            "status": "correct" if title_num == i else "naming_error"
        }

    return chapters


def build_index(chapters: Dict[int, Dict], total_planned: int = 360) -> Dict:
    """构建索引数据"""

    # 统计信息
    total_files = len(chapters)
    correct_files = sum(1 for c in chapters.values() if c["status"] == "correct")
    naming_errors = sum(1 for c in chapters.values() if c["status"] == "naming_error")

    # 缺失章节号
    file_nums = set(chapters.keys())
    all_nums = set(range(0, total_planned + 1))
    missing_files = sorted(all_nums - file_nums)

    # 缺失章节号（基于标题）
    title_nums = set(c["title_num"] for c in chapters.values() if c["title_num"])
    expected_titles = set(range(1, total_planned + 1))
    missing_titles = sorted(expected_titles - title_nums)

    # 命名问题列表
    naming_issues = [
        {"file": c["file"], "file_num": c["file_num"], "title_num": c["title_num"]}
        for c in chapters.values() if c["status"] == "naming_error"
    ]

    return {
        "version": "v1.0",
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "total_planned": total_planned,
        "total_files": total_files,
        "correct_files": correct_files,
        "naming_errors": naming_errors,
        "missing_files": missing_files,
        "missing_titles": missing_titles,
        "naming_issues": naming_issues,
        "chapters": chapters
    }


def save_index(index: Dict, output_path: str):
    """保存索引到文件"""
    # 不保存完整的 chapters 太冗余，只保存摘要
    summary = {
        "version": index["version"],
        "updated": index["updated"],
        "total_planned": index["total_planned"],
        "total_files": index["total_files"],
        "correct_files": index["correct_files"],
        "naming_errors": index["naming_errors"],
        "missing_files": index["missing_files"],
        "missing_titles": index["missing_titles"],
        "naming_issues": index["naming_issues"],
        "chapter_count": len(index["chapters"])
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def query_chapter(chapters: Dict[int, Dict], query: str) -> Optional[Dict]:
    """查询指定章节"""
    # 支持 ch001, 001, 1, 1-10 等格式
    if query.startswith('ch'):
        query = query[2:].replace('.md', '')

    try:
        num = int(query)
        return chapters.get(num)
    except ValueError:
        pass

    # 模糊匹配标题
    results = []
    for c in chapters.values():
        if query.lower() in c["title"].lower():
            results.append(c)

    return results if results else None


def main():
    parser = argparse.ArgumentParser(description='章节文件索引管理')
    parser.add_argument('--all', action='store_true', help='更新全部索引')
    parser.add_argument('--query', type=str, help='查询指定章节（如 ch078）')
    parser.add_argument('--missing', action='store_true', help='检查缺失章节')
    parser.add_argument('--verify', action='store_true', help='验证索引一致性')
    parser.add_argument('--output', type=str, default='index.json', help='索引输出文件')

    args = parser.parse_args()

    chapter_dir = os.path.dirname(os.path.abspath(__file__))

    # 首先扫描章节
    chapters = scan_chapters(chapter_dir)
    index = build_index(chapters)

    if args.query:
        # 查询单个章节
        result = query_chapter(chapters, args.query)

        if isinstance(result, dict):
            print(f"找到章节: {result['file']}")
            print(f"  文件编号: {result['file_num']}")
            print(f"  标题章节号: {result['title_num']}")
            print(f"  标题: {result['title']}")
            print(f"  状态: {result['status']}")
        elif isinstance(result, list):
            print(f"找到 {len(result)} 个匹配:")
            for r in result:
                print(f"  {r['file']}: {r['title']}")
        else:
            print(f"未找到章节: {args.query}")

    elif args.missing:
        # 检查缺失章节
        print("=" * 60)
        print("缺失章节检查")
        print("=" * 60)

        print(f"\n缺失文件编号: {index['missing_files']}")
        print(f"缺失章节号: {index['missing_titles']}")

        if index['missing_titles']:
            print("\n缺失章节详情:")
            for m in index['missing_titles'][:10]:
                prev_ch = m - 1 if m > 1 else None
                next_ch = m + 1 if m < 360 else None
                prev_info = chapters.get(prev_ch, {}).get("title", "无") if prev_ch else "无"
                next_info = chapters.get(next_ch, {}).get("title", "无") if next_ch else "无"
                print(f"  章节{m}:")
                print(f"    前: {prev_info}")
                print(f"    后: {next_info}")

    elif args.verify:
        # 验证索引一致性
        print("=" * 60)
        print("索引一致性验证")
        print("=" * 60)

        all_correct = True

        if index['naming_errors'] > 0:
            print(f"\n❌ 发现 {index['naming_errors']} 个命名错误")
            all_correct = False
        else:
            print("\n✅ 所有文件命名正确")

        if index['missing_files']:
            print(f"\n❌ 缺失 {len(index['missing_files'])} 个文件")
            all_correct = False
        else:
            print("\n✅ 无文件缺失")

        if index['missing_titles']:
            print(f"\n⚠️  缺失 {len(index['missing_titles'])} 个章节号（内容缺失）")
            all_correct = False

        if all_correct:
            print("\n✅ 索引验证通过")

    else:
        # 默认：更新全部索引
        output_path = os.path.join(chapter_dir, args.output)
        save_index(index, output_path)

        print("=" * 60)
        print("章节文件索引更新完成")
        print("=" * 60)
        print(f"总文件数: {index['total_files']}")
        print(f"正确文件: {index['correct_files']}")
        print(f"命名错误: {index['naming_errors']}")
        print(f"缺失文件: {len(index['missing_files'])} 个")
        print(f"缺失章节号: {index['missing_titles'][:10]}...")

        if index['naming_issues']:
            print("\n命名问题文件:")
            for issue in index['naming_issues'][:5]:
                print(f"  {issue['file']}: 文件号={issue['file_num']}, 章节号={issue['title_num']}")

        print(f"\n索引已保存到: {output_path}")
        chapters = scan_chapters(chapter_dir)
        index = build_index(chapters)

        print("=" * 60)
        print("索引一致性验证")
        print("=" * 60)

        all_correct = True

        if index['naming_errors'] > 0:
            print(f"\n❌ 发现 {index['naming_errors']} 个命名错误")
            all_correct = False
        else:
            print("\n✅ 所有文件命名正确")

        if index['missing_files']:
            print(f"\n❌ 缺失 {len(index['missing_files'])} 个文件")
            all_correct = False
        else:
            print("\n✅ 无文件缺失")

        if index['missing_titles']:
            print(f"\n⚠️  缺失 {len(index['missing_titles'])} 个章节号（内容缺失）")
            all_correct = False

        if all_correct:
            print("\n✅ 索引验证通过")


if __name__ == "__main__":
    main()