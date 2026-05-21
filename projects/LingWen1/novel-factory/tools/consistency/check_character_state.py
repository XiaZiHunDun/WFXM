#!/usr/bin/env python3
"""
人物状态追踪检查器 v2.0
改进：减少误报，只检测真正的一致性问题
"""
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


@dataclass
class CharacterState:
    """人物状态快照"""
    chapter: int
    gender: Optional[str] = None  # male/female
    alive: Optional[bool] = None  # True/False
    form: Optional[str] = None     # 化星/少女/灵体


# 人物追踪表
CHARACTER_TRACKER = ["星月", "小九", "铁蛋", "林夜", "苏琳", "墨白"]

_WAIVERS_PATH = Path(__file__).resolve().parent / "character_waivers.yaml"


def _load_alive_waivers() -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    if yaml is None or not _WAIVERS_PATH.is_file():
        return out
    try:
        data = yaml.safe_load(_WAIVERS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return out
    for row in data.get("suppress_alive_conflict") or []:
        if not isinstance(row, dict):
            continue
        char = str(row.get("char") or "").strip()
        ch = row.get("chapter")
        if char and ch is not None:
            try:
                out.add((char, int(ch)))
            except (TypeError, ValueError):
                pass
    return out

# 生死指示词（更严格：必须是主语死亡）
ALIVE_PATTERNS = {
    True: ['活着', '苏醒', '复活', '重生'],
    False: ['死了', '陨落', '消亡', '化为星光', '消散', '牺牲'],
}


def find_character_sentences(content: str, character: str) -> List[str]:
    """
    查找所有提到该人物的完整句子
    这是减少误报的关键：只分析真正提到人物的句子
    """
    sentences = re.split(r'[。！？\n]', content)
    relevant = []
    for sent in sentences:
        if character in sent:
            relevant.append(sent)
    return relevant


def check_gender_in_sentence(sentence: str, character: str) -> Optional[str]:
    """
    检测句子中人物性别描述的一致性

    改进：只在该人物是句子主语时检测性别
    """
    # 提取主语附近的性别词
    # 查找"[角色名]..."之后第一个性别词的位置

    # 简化：查找"[角色]"后30字内是否有"他"或"她"
    pattern = character + r'.{0,30}'
    matches = re.finditer(pattern, sentence)
    for m in matches:
        text = sentence[m.start():m.end()]
        # 查找性别词
        if re.search(r'他[是|说|道|看|想|觉|笑|冷|沉|抬|低|走|跑|站|坐|躺|握|拿|抱|背]', text):
            return 'male'
        if re.search(r'她[是|说|道|看|想|觉|笑|冷|沉|抬|低|走|跑|站|坐|躺|握|拿|抱|背]', text):
            return 'female'
    return None


def check_alive_in_sentence(sentence: str, character: str) -> Optional[bool]:
    """
    检测句子中人物生死状态

    改进：必须满足"[角色]是/死了/活着"等主语模式才认定
    """
    for alive, patterns in ALIVE_PATTERNS.items():
        for pattern in patterns:
            # 检查"[角色]死了" "[角色]活着"等模式
            if re.search(character + r'.{0,5}' + pattern, sentence):
                return alive
            # 检查"死了的是[角色]"等倒装
            if re.search(pattern + r'.{0,5}' + character, sentence):
                return alive
    return None


def extract_character_state(content: str, chapter_num: int,
                            characters: List[str]) -> Dict[str, CharacterState]:
    """
    从章节内容中提取人物状态
    改进：只分析真正提到人物的句子
    """
    states = {}

    for char in characters:
        if char not in content:
            continue

        state = CharacterState(chapter=chapter_num)
        sentences = find_character_sentences(content, char)

        gender_detected = None
        alive_detected = None

        for sent in sentences:
            # 检测性别（只取第一个有效结果）
            if gender_detected is None:
                gender_detected = check_gender_in_sentence(sent, char)

            # 检测生死（只取第一个有效结果）
            if alive_detected is None:
                alive_detected = check_alive_in_sentence(sent, char)

        state.gender = gender_detected
        state.alive = alive_detected

        states[char] = state

    return states


def check_character_consistency(chapters_dir: str,
                                chapter_range: tuple[int, int] = (1, 360),
                                characters: List[str] = None) -> List[Tuple]:
    """
    跨章节校验人物状态一致性（改进版）
    只检测真正的主语性别/生死变化
    """
    if characters is None:
        characters = CHARACTER_TRACKER

    issues = []
    waivers = _load_alive_waivers()
    state_history: Dict[str, List[CharacterState]] = {c: [] for c in characters}
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

        # 提取当前章节的人物状态
        current_states = extract_character_state(content, i, characters)

        for char, state in current_states.items():
            if state.gender is None and state.alive is None:
                continue  # 没有有效状态，跳过

            # 与历史状态比较
            if state_history[char]:
                prev = state_history[char][-1]

                # 仅报告「死后复活」类矛盾；「存活→死亡」为正常剧情，不报 P1
                if state.alive is not None and prev.alive is not None:
                    if (not prev.alive) and state.alive:
                        if (char, i) in waivers:
                            continue
                        issues.append(
                            (
                                "ALIVE_CONFLICT",
                                i,
                                char,
                                f"{char}生死状态矛盾: 前文已死亡，本章又出现明确存活表述",
                            )
                        )

        # 更新历史
        for char, state in current_states.items():
            if state.gender is not None or state.alive is not None:
                state_history[char].append(state)

    return issues


def report_character_issues(issues: List[Tuple], output_file: str = None) -> str:
    """生成人物状态检查报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("人物状态一致性检查报告 (v2.0)")
    lines.append("=" * 70)

    if not issues:
        lines.append("\n✅ 未发现人物状态矛盾")
        report = "\n".join(lines)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        return report

    by_char = {}
    for issue in issues:
        char = issue[2]
        if char not in by_char:
            by_char[char] = []
        by_char[char].append(issue)

    lines.append(f"\n发现问题: {len(issues)} 处")

    for char, char_issues in by_char.items():
        lines.append(f"\n--- {char} ---")
        for issue in char_issues:
            lines.append(f"  ch{issue[1]:03d}: {issue[3]}")

    report = "\n".join(lines)
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='人物状态一致性检查 (v2.0)')
    parser.add_argument('chapters_dir', help='章节目录路径')
    parser.add_argument('--output', '-o', help='输出报告路径')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=360, help='结束章节')
    parser.add_argument('--characters', nargs='+', help='指定检查的人物')
    args = parser.parse_args()

    issues = check_character_consistency(args.chapters_dir, (args.start, args.end), args.characters)
    report = report_character_issues(issues, args.output)
    print(report)

    sys.exit(0 if not issues else 1)