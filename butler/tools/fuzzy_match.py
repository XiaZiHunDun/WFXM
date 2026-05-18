#!/usr/bin/env python3
"""
Fuzzy matching for Butler file/editing operations (ported from Hermes Agent).

Implements a multi-strategy matching chain to find and replace text despite
common LLM/tool transport drift (whitespace, indentation, escaping, Unicode).

Strategies are tried in order:
1. exact — direct string comparison
2. line_trimmed — strip leading/trailing whitespace per line
3. whitespace_normalized — collapse runs of spaces/tabs
4. indentation_flexible — ignore indentation (lstrip per line)
5. escape_normalized — convert \\n/\\t/\\r escapes to real characters
6. trimmed_boundary — trim first/last line boundaries only
7. unicode_normalized — smart quotes, dashes, ellipsis, NBSP → ASCII
8. block_anchor — first + last line anchors; SequenceMatcher on middle
9. context_aware — 80% similar lines for ≥50% of pattern lines

All stdlib-only; Hermes-local imports removed.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

UNICODE_MAP = {
    "\u201c": '"',
    "\u201d": '"',  # smart double quotes
    "\u2018": "'",
    "\u2019": "'",  # smart single quotes
    "\u2014": "--",
    "\u2013": "-",  # em/en dashes
    "\u2026": "...",
    "\u00a0": " ",  # ellipsis and non-breaking space
}


def _unicode_normalize(text: str) -> str:
    """Map common Unicode typography to ASCII equivalents."""
    for char, repl in UNICODE_MAP.items():
        text = text.replace(char, repl)
    return text


def fuzzy_find_and_replace(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> tuple[str, int, str | None, str | None]:
    """
    Find and replace text using progressively fuzzier matching strategies.

    Returns:
        (new_content, match_count, strategy_name, error_message)
        On success error_message is None; on failure strategy_name is None.
    """
    if not old_string:
        return content, 0, None, "old_string cannot be empty"

    if old_string == new_string:
        return content, 0, None, "old_string and new_string are identical"

    strategies: list[tuple[str, object]] = [
        ("exact", _strategy_exact),
        ("line_trimmed", _strategy_line_trimmed),
        ("whitespace_normalized", _strategy_whitespace_normalized),
        ("indentation_flexible", _strategy_indentation_flexible),
        ("escape_normalized", _strategy_escape_normalized),
        ("trimmed_boundary", _strategy_trimmed_boundary),
        ("unicode_normalized", _strategy_unicode_normalized),
        ("block_anchor", _strategy_block_anchor),
        ("context_aware", _strategy_context_aware),
    ]

    FUZZY_STRATEGIES = {"block_anchor", "context_aware"}
    MIN_CONFIDENCE = 0.75

    for strategy_name, strategy_fn in strategies:
        matches = strategy_fn(content, old_string)

        if matches:
            if len(matches) > 1 and not replace_all:
                return content, 0, None, (
                    f"Found {len(matches)} matches for old_string. "
                    f"Provide more context to make it unique, or use replace_all=True."
                )

            if strategy_name != "exact":
                drift_err = _detect_escape_drift(content, matches, old_string, new_string)
                if drift_err:
                    return content, 0, None, drift_err

            if strategy_name in FUZZY_STRATEGIES:
                confidence = _calculate_match_confidence(
                    content, matches, old_string
                )
                if confidence < MIN_CONFIDENCE:
                    return content, 0, None, (
                        f"模糊匹配置信度过低 ({confidence:.0%} < {MIN_CONFIDENCE:.0%})，"
                        f"使用的策略: {strategy_name}。"
                        f"请先使用 read_file 查看文件最新内容，"
                        f"再提供更精确的 old_text。"
                    )

            new_content = _apply_replacements(content, matches, new_string)
            return new_content, len(matches), strategy_name, None

    return content, 0, None, "Could not find a match for old_string in the file"


def fuzzy_replace(old_text: str, new_text: str, content: str) -> tuple[str | None, str]:
    """Legacy interface. Returns (new_content, strategy_or_error)."""
    new_content, count, strategy, error = fuzzy_find_and_replace(
        content, old_text, new_text
    )
    if count == 0:
        hint = format_no_match_hint(error, count, old_text, content)
        return None, (error or "未找到匹配文本") + hint
    return new_content, strategy or "exact"


def _detect_escape_drift(
    content: str,
    matches: list[tuple[int, int]],
    old_string: str,
    new_string: str,
) -> str | None:
    """Detect misleading \\' / \\" serialization from tool transports."""
    if "\\'" not in new_string and '\\"' not in new_string:
        return None

    matched_regions = "".join(content[start:end] for start, end in matches)

    for suspect in ("\\'", '\\"'):
        if suspect in new_string and suspect in old_string and suspect not in matched_regions:
            plain = suspect[1]
            return (
                f"Escape-drift detected: old_string and new_string contain "
                f"the literal sequence {suspect!r} but the matched region of "
                f"the file does not. This is almost always a tool-call "
                f"serialization artifact where an apostrophe or quote got "
                f"prefixed with a spurious backslash. Re-read the file with "
                f"read_file and pass old_string/new_string without "
                f"backslash-escaping {plain!r} characters."
            )
    return None


def _apply_replacements(
    content: str,
    matches: list[tuple[int, int]],
    new_string: str,
) -> str:
    sorted_matches = sorted(matches, key=lambda x: x[0], reverse=True)
    result = content
    for start, end in sorted_matches:
        result = result[:start] + new_string + result[end:]
    return result


def _calculate_match_confidence(
    content: str,
    matches: list[tuple[int, int]],
    old_string: str,
) -> float:
    """Calculate confidence score for fuzzy matches (0.0 - 1.0)."""
    if not matches:
        return 0.0
    total_ratio = 0.0
    for start, end in matches:
        matched_text = content[start:end]
        ratio = SequenceMatcher(None, old_string, matched_text).ratio()
        total_ratio += ratio
    return total_ratio / len(matches)


# --- Strategies ---


def _strategy_exact(content: str, pattern: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    start = 0
    while True:
        pos = content.find(pattern, start)
        if pos == -1:
            break
        matches.append((pos, pos + len(pattern)))
        start = pos + 1
    return matches


def _strategy_line_trimmed(content: str, pattern: str) -> list[tuple[int, int]]:
    pattern_lines = [line.strip() for line in pattern.split("\n")]
    pattern_normalized = "\n".join(pattern_lines)
    content_lines = content.split("\n")
    content_normalized_lines = [line.strip() for line in content_lines]
    return _find_normalized_matches(
        content,
        content_lines,
        content_normalized_lines,
        pattern,
        pattern_normalized,
    )


def _strategy_whitespace_normalized(content: str, pattern: str) -> list[tuple[int, int]]:
    def normalize(s: str) -> str:
        return re.sub(r"[ \t]+", " ", s)

    pattern_normalized = normalize(pattern)
    content_normalized = normalize(content)
    matches_in_normalized = _strategy_exact(content_normalized, pattern_normalized)
    if not matches_in_normalized:
        return []
    return _map_normalized_positions(content, content_normalized, matches_in_normalized)


def _strategy_indentation_flexible(content: str, pattern: str) -> list[tuple[int, int]]:
    content_lines = content.split("\n")
    content_stripped_lines = [line.lstrip() for line in content_lines]
    pattern_lines = [line.lstrip() for line in pattern.split("\n")]
    return _find_normalized_matches(
        content,
        content_lines,
        content_stripped_lines,
        pattern,
        "\n".join(pattern_lines),
    )


def _strategy_escape_normalized(content: str, pattern: str) -> list[tuple[int, int]]:
    def unescape(s: str) -> str:
        return s.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")

    pattern_unescaped = unescape(pattern)
    if pattern_unescaped == pattern:
        return []
    return _strategy_exact(content, pattern_unescaped)


def _strategy_trimmed_boundary(content: str, pattern: str) -> list[tuple[int, int]]:
    pattern_lines = pattern.split("\n")
    if not pattern_lines:
        return []
    pattern_lines = list(pattern_lines)
    pattern_lines[0] = pattern_lines[0].strip()
    if len(pattern_lines) > 1:
        pattern_lines[-1] = pattern_lines[-1].strip()
    modified_pattern = "\n".join(pattern_lines)
    content_lines = content.split("\n")
    matches: list[tuple[int, int]] = []
    pattern_line_count = len(pattern_lines)
    for i in range(len(content_lines) - pattern_line_count + 1):
        block_lines = content_lines[i : i + pattern_line_count]
        check_lines = list(block_lines)
        check_lines[0] = check_lines[0].strip()
        if len(check_lines) > 1:
            check_lines[-1] = check_lines[-1].strip()
        if "\n".join(check_lines) == modified_pattern:
            start_pos, end_pos = _calculate_line_positions(
                content_lines, i, i + pattern_line_count, len(content)
            )
            matches.append((start_pos, end_pos))
    return matches


def _build_orig_to_norm_map(original: str) -> list[int]:
    result: list[int] = []
    norm_pos = 0
    for char in original:
        result.append(norm_pos)
        repl = UNICODE_MAP.get(char)
        norm_pos += len(repl) if repl is not None else 1
    result.append(norm_pos)
    return result


def _map_positions_norm_to_orig(
    orig_to_norm: list[int],
    norm_matches: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    norm_to_orig_start: dict[int, int] = {}
    for orig_pos, norm_pos in enumerate(orig_to_norm[:-1]):
        if norm_pos not in norm_to_orig_start:
            norm_to_orig_start[norm_pos] = orig_pos

    results: list[tuple[int, int]] = []
    orig_len = len(orig_to_norm) - 1

    for norm_start, norm_end in norm_matches:
        if norm_start not in norm_to_orig_start:
            continue
        orig_start = norm_to_orig_start[norm_start]
        orig_end = orig_start
        while orig_end < orig_len and orig_to_norm[orig_end] < norm_end:
            orig_end += 1
        results.append((orig_start, orig_end))

    return results


def _strategy_unicode_normalized(content: str, pattern: str) -> list[tuple[int, int]]:
    norm_pattern = _unicode_normalize(pattern)
    norm_content = _unicode_normalize(content)
    if norm_content == content and norm_pattern == pattern:
        return []

    norm_matches = _strategy_exact(norm_content, norm_pattern)
    if not norm_matches:
        norm_matches = _strategy_line_trimmed(norm_content, norm_pattern)
    if not norm_matches:
        return []

    orig_to_norm = _build_orig_to_norm_map(content)
    return _map_positions_norm_to_orig(orig_to_norm, norm_matches)


def _strategy_block_anchor(content: str, pattern: str) -> list[tuple[int, int]]:
    norm_pattern = _unicode_normalize(pattern)
    norm_content = _unicode_normalize(content)
    pattern_lines = norm_pattern.split("\n")
    if len(pattern_lines) < 2:
        return []

    first_line = pattern_lines[0].strip()
    last_line = pattern_lines[-1].strip()
    norm_content_lines = norm_content.split("\n")
    orig_content_lines = content.split("\n")
    pattern_line_count = len(pattern_lines)

    potential_matches: list[int] = []
    for i in range(len(norm_content_lines) - pattern_line_count + 1):
        if (
            norm_content_lines[i].strip() == first_line
            and norm_content_lines[i + pattern_line_count - 1].strip() == last_line
        ):
            potential_matches.append(i)

    matches: list[tuple[int, int]] = []
    candidate_count = len(potential_matches)
    threshold = 0.50 if candidate_count == 1 else 0.70

    for i in potential_matches:
        if pattern_line_count <= 2:
            similarity = 1.0
        else:
            content_middle = "\n".join(
                norm_content_lines[i + 1 : i + pattern_line_count - 1]
            )
            pattern_middle = "\n".join(pattern_lines[1:-1])
            similarity = SequenceMatcher(None, content_middle, pattern_middle).ratio()
        if similarity >= threshold:
            start_pos, end_pos = _calculate_line_positions(
                orig_content_lines, i, i + pattern_line_count, len(content)
            )
            matches.append((start_pos, end_pos))
    return matches


def _strategy_context_aware(content: str, pattern: str) -> list[tuple[int, int]]:
    pattern_lines = pattern.split("\n")
    content_lines = content.split("\n")
    if not pattern_lines:
        return []

    matches: list[tuple[int, int]] = []
    pattern_line_count = len(pattern_lines)
    for i in range(len(content_lines) - pattern_line_count + 1):
        block_lines = content_lines[i : i + pattern_line_count]
        high_similarity_count = 0
        for p_line, c_line in zip(pattern_lines, block_lines):
            sim = SequenceMatcher(None, p_line.strip(), c_line.strip()).ratio()
            if sim >= 0.80:
                high_similarity_count += 1
        if high_similarity_count >= len(pattern_lines) * 0.5:
            start_pos, end_pos = _calculate_line_positions(
                content_lines, i, i + pattern_line_count, len(content)
            )
            matches.append((start_pos, end_pos))
    return matches


# --- Helpers ---


def _calculate_line_positions(
    content_lines: list[str],
    start_line: int,
    end_line: int,
    content_length: int,
) -> tuple[int, int]:
    start_pos = sum(len(line) + 1 for line in content_lines[:start_line])
    end_pos = sum(len(line) + 1 for line in content_lines[:end_line]) - 1
    if end_pos >= content_length:
        end_pos = content_length
    return start_pos, end_pos


def _find_normalized_matches(
    content: str,
    content_lines: list[str],
    content_normalized_lines: list[str],
    pattern: str,
    pattern_normalized: str,
) -> list[tuple[int, int]]:
    pattern_norm_lines = pattern_normalized.split("\n")
    num_pattern_lines = len(pattern_norm_lines)
    matches: list[tuple[int, int]] = []
    for i in range(len(content_normalized_lines) - num_pattern_lines + 1):
        block = "\n".join(content_normalized_lines[i : i + num_pattern_lines])
        if block == pattern_normalized:
            start_pos, end_pos = _calculate_line_positions(
                content_lines, i, i + num_pattern_lines, len(content)
            )
            matches.append((start_pos, end_pos))
    return matches


def _map_normalized_positions(
    original: str,
    normalized: str,
    normalized_matches: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if not normalized_matches:
        return []

    orig_to_norm: list[int] = []
    orig_idx = 0
    norm_idx = 0
    while orig_idx < len(original) and norm_idx < len(normalized):
        if original[orig_idx] == normalized[norm_idx]:
            orig_to_norm.append(norm_idx)
            orig_idx += 1
            norm_idx += 1
        elif original[orig_idx] in " \t" and normalized[norm_idx] == " ":
            orig_to_norm.append(norm_idx)
            orig_idx += 1
            if orig_idx < len(original) and original[orig_idx] not in " \t":
                norm_idx += 1
        elif original[orig_idx] in " \t":
            orig_to_norm.append(norm_idx)
            orig_idx += 1
        else:
            orig_to_norm.append(norm_idx)
            orig_idx += 1
    while orig_idx < len(original):
        orig_to_norm.append(len(normalized))
        orig_idx += 1

    norm_to_orig_start: dict[int, int] = {}
    norm_to_orig_end: dict[int, int] = {}
    for orig_pos, norm_pos in enumerate(orig_to_norm):
        if norm_pos not in norm_to_orig_start:
            norm_to_orig_start[norm_pos] = orig_pos
        norm_to_orig_end[norm_pos] = orig_pos

    original_matches: list[tuple[int, int]] = []
    for norm_start, norm_end in normalized_matches:
        if norm_start in norm_to_orig_start:
            orig_start = norm_to_orig_start[norm_start]
        else:
            orig_start = min(i for i, n in enumerate(orig_to_norm) if n >= norm_start)
        if norm_end - 1 in norm_to_orig_end:
            orig_end = norm_to_orig_end[norm_end - 1] + 1
        else:
            orig_end = orig_start + (norm_end - norm_start)
        while orig_end < len(original) and original[orig_end] in " \t":
            orig_end += 1
        original_matches.append((orig_start, min(orig_end, len(original))))
    return original_matches


def find_closest_lines(
    old_string: str,
    content: str,
    context_lines: int = 2,
    max_results: int = 3,
) -> str:
    """Find content lines most similar to ``old_string`` for user feedback."""
    if not old_string or not content:
        return ""

    old_lines = old_string.splitlines()
    content_lines = content.splitlines()
    if not old_lines or not content_lines:
        return ""

    anchor = old_lines[0].strip()
    if not anchor:
        candidates = [l.strip() for l in old_lines if l.strip()]
        if not candidates:
            return ""
        anchor = candidates[0]

    scored: list[tuple[float, int]] = []
    for i, line in enumerate(content_lines):
        stripped = line.strip()
        if not stripped:
            continue
        ratio = SequenceMatcher(None, anchor, stripped).ratio()
        if ratio > 0.3:
            scored.append((ratio, i))

    if not scored:
        return ""

    scored.sort(key=lambda x: -x[0])
    top = scored[:max_results]
    parts: list[str] = []
    seen_ranges: set[tuple[int, int]] = set()
    for _, line_idx in top:
        start = max(0, line_idx - context_lines)
        end = min(len(content_lines), line_idx + len(old_lines) + context_lines)
        key = (start, end)
        if key in seen_ranges:
            continue
        seen_ranges.add(key)
        snippet = "\n".join(
            f"{start + j + 1:4d}| {content_lines[start + j]}"
            for j in range(end - start)
        )
        parts.append(snippet)
    if not parts:
        return ""
    return "\n---\n".join(parts)


def format_no_match_hint(
    error: str | None,
    match_count: int,
    old_string: str,
    content: str,
) -> str:
    """Append a 'Did you mean…' block for plain not-found errors only."""
    if match_count != 0:
        return ""
    if not error or not error.startswith("Could not find"):
        return ""
    hint = find_closest_lines(old_string, content)
    if not hint:
        return ""
    return "\n\nDid you mean one of these sections?\n" + hint
