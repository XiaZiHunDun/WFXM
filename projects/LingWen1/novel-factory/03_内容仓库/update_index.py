#!/usr/bin/env python3
"""
内容仓库索引生成脚本
用法：
  python update_index.py --layer volume     # 更新卷大纲索引
  python update_index.py --layer stage      # 更新阶段大纲索引
  python update_index.py --layer chapter    # 更新正文索引
  python update_index.py --query ch001      # 查询ch001状态
  python update_index.py --range ch001 ch010  # 查询ch001-010列表
  python update_index.py --update ch001    # 更新ch001的索引（作家提交后调用）
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime

CONTENT_ROOT = Path(__file__).parent.absolute()

def get_chapter_info(chapter_file):
    """从正文章节文件获取基本信息"""
    with open(chapter_file, 'r', encoding='utf-8') as f:
        content = f.read()
    return {
        "filename": chapter_file.name,
        "word_count": len(content),
        "char_count": len(content.replace('\n', '').replace(' ', '')),
        "lines": content.count('\n'),
        "last_updated": datetime.fromtimestamp(os.path.getmtime(chapter_file)).strftime('%Y-%m-%d')
    }

def update_chapter_index():
    """更新正文目录索引（04_正文/index.json）"""
    chapters_dir = CONTENT_ROOT / "04_正文"
    index_file = chapters_dir / "index.json"

    chapters = []
    for f in sorted(chapters_dir.glob("ch*.md")):
        if f.is_file():
            info = get_chapter_info(f)
            chapters.append({
                "chapter": f.stem,  # e.g. "ch001"
                **info
            })

    index_data = {
        "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_chapters": len(chapters),
        "chapters": chapters
    }

    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"Updated chapter index: {len(chapters)} chapters")
    return index_data

def update_stage_index(volume=None):
    """更新阶段大纲索引（03_阶段大纲/*/index.json）"""
    stages_dir = CONTENT_ROOT / "03_阶段大纲"

    for stage_dir in stages_dir.rglob("*/"):
        if stage_dir.is_dir():
            index_file = stage_dir / "index.json"
            stage_files = list(stage_dir.glob("*.md"))

            stages = []
            for f in stage_files:
                if f.name != "index.json":
                    stages.append({
                        "filename": f.name,
                        "last_updated": datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d')
                    })

            index_data = {
                "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_files": len(stages),
                "files": stages
            }

            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"Updated stage indices")

def update_volume_index():
    """更新卷大纲索引（02_卷大纲/*/index.json）"""
    volumes_dir = CONTENT_ROOT / "02_卷大纲"

    for volume_dir in volumes_dir.rglob("*/"):
        if volume_dir.is_dir():
            index_file = volume_dir / "index.json"
            volume_files = list(volume_dir.glob("*.md"))

            volumes = []
            for f in volume_files:
                if f.name != "index.json":
                    volumes.append({
                        "filename": f.name,
                        "last_updated": datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d')
                    })

            index_data = {
                "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_files": len(volumes),
                "files": volumes
            }

            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"Updated volume indices")

def update_full_index():
    """更新全文大纲索引（01_全文总体大纲/index.json）"""
    full_dir = CONTENT_ROOT / "01_全文总体大纲"
    index_file = full_dir / "index.json"

    full_files = [f for f in full_dir.glob("*.md") if f.name != "index.json"]

    full_data = []
    for f in full_files:
        full_data.append({
            "filename": f.name,
            "last_updated": datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d')
        })

    index_data = {
        "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_files": len(full_data),
        "files": full_data
    }

    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"Updated full novel index")

def update_all():
    """更新所有索引"""
    update_full_index()
    update_volume_index()
    update_stage_index()
    update_chapter_index()
    print("All indices updated")

def query_chapter(chapter_name):
    """查询指定章节信息"""
    chapter_file = CONTENT_ROOT / "04_正文" / f"{chapter_name}.md"
    if not chapter_file.exists():
        print(f"Chapter {chapter_name} not found")
        return None

    info = get_chapter_info(chapter_file)
    print(f"Chapter: {chapter_name}")
    print(f"  Word count: {info['word_count']}")
    print(f"  Last updated: {info['last_updated']}")
    return info

def query_range(start_ch, end_ch):
    """查询章节范围"""
    chapters_dir = CONTENT_ROOT / "04_正文"
    result = []

    # 解析章节范围
    start_num = int(start_ch.replace('ch', ''))
    end_num = int(end_ch.replace('ch', ''))

    for i in range(start_num, end_num + 1):
        ch_name = f"ch{str(i).zfill(3)}"
        chapter_file = chapters_dir / f"{ch_name}.md"
        if chapter_file.exists():
            info = get_chapter_info(chapter_file)
            result.append(info)

    print(f"Range {start_ch}-{end_ch}: {len(result)} chapters")
    return result

def main():
    parser = argparse.ArgumentParser(description='内容仓库索引管理脚本')
    parser.add_argument('--layer', choices=['full', 'volume', 'stage', 'chapter'],
                        help='指定更新的层级')
    parser.add_argument('--update', help='更新单个章节索引（章节名，如ch001）')
    parser.add_argument('--query', help='查询单个章节信息')
    parser.add_argument('--range', nargs=2, metavar=('START', 'END'),
                        help='查询章节范围，如 --range ch001 ch010')
    parser.add_argument('--all', action='store_true', help='更新所有索引')

    args = parser.parse_args()

    if args.all:
        update_all()
    elif args.layer:
        if args.layer == 'full':
            update_full_index()
        elif args.layer == 'volume':
            update_volume_index()
        elif args.layer == 'stage':
            update_stage_index()
        elif args.layer == 'chapter':
            update_chapter_index()
    elif args.update:
        update_chapter_index()
    elif args.query:
        query_chapter(args.query)
    elif args.range:
        query_range(args.range[0], args.range[1])
    else:
        parser.print_help()

if __name__ == '__main__':
    main()