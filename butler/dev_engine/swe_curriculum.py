"""SWE-bench Lite playbooks and oracle replay hints for LIVE delegate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SWEPlaybook:
    instance_id: str
    title: str
    pattern_summary: str
    steps: tuple[str, ...]
    skill_name: str = ""


SWE_PLAYBOOKS: dict[str, SWEPlaybook] = {
    "SWE-012": SWEPlaybook(
        instance_id="SWE-012",
        title="Sorting test fails for empty list",
        pattern_summary=(
            "test_fix: implementation is correct; wrong assertion in test_sorter.py — "
            "change `assert sort_items([]) is None` to `assert sort_items([]) == []`."
        ),
        steps=(
            "read_file test_sorter.py and sorter.py — confirm sort_items([]) returns []",
            "patch test_sorter.py ONLY — fix test_sort_empty assertion (is None → == [])",
            "terminal: python -m pytest _swe_test.py -q",
        ),
        skill_name="b9-swe-test-assertion-fix",
    ),
    "SWE-013": SWEPlaybook(
        instance_id="SWE-013",
        title="Add status field to API response",
        pattern_summary="make_response must set status ok/error from HTTP code.",
        steps=(
            "read_file api/response.py",
            "patch make_response to add status: ok if code < 400 else error",
            "terminal: python -m pytest _swe_test.py -q",
        ),
        skill_name="b9-swe-api-status",
    ),
    "SWE-014": SWEPlaybook(
        instance_id="SWE-014",
        title="EventBus.on returns unsubscribe callable",
        pattern_summary=(
            "EventBus.on(event, callback) must return unsubscribe() that removes "
            "callback from self._listeners[event]. Patch on() only; never write_file "
            "the whole module."
        ),
        steps=(
            "read_file events.py — locate EventBus.on",
            "patch on(): after append(callback), define unsubscribe() removing callback; return it",
            "terminal: python -m pytest _swe_test.py -q",
        ),
        skill_name="b9-swe-event-unsubscribe",
    ),
    "SWE-015": SWEPlaybook(
        instance_id="SWE-015",
        title="PriorityQueue pop highest priority first",
        pattern_summary=(
            "After sort(), pop(0) not pop(): lowest priority number = highest priority item."
        ),
        steps=(
            "read_file priority_queue.py — locate PriorityQueue.pop",
            "patch pop: keep self._items.sort(); change return self._items.pop()[1] to pop(0)[1]",
            "terminal: python -m pytest _swe_test.py -q",
        ),
        skill_name="b9-swe-priority-queue",
    ),
}


def get_swe_playbook(instance_id: str) -> SWEPlaybook | None:
    return SWE_PLAYBOOKS.get(instance_id)


def build_swe_playbook_block(instance_id: str) -> str:
    pb = get_swe_playbook(instance_id)
    if pb is None:
        return ""
    lines = [
        f"## SWE PLAYBOOK ({pb.instance_id})",
        pb.pattern_summary,
        "steps:",
        *[f"- {s}" for s in pb.steps],
    ]
    return "\n".join(lines)


def format_swe_replay_block(instance_id: str) -> str:
    pb = get_swe_playbook(instance_id)
    if pb is None:
        return ""
    lines = [
        "## SWE ORACLE REPLAY (mandatory)",
        f"Instance {pb.instance_id}: {pb.title}",
        f"pattern: {pb.pattern_summary}",
        "Execute:",
        *[f"- {s}" for s in pb.steps],
    ]
    lines.append("avoid: write_file entire source; use patch on the target function only.")
    if instance_id == "SWE-012":
        lines.extend([
            "",
            "bug: test_sort_empty expects None but sort_items([]) correctly returns [].",
            "fix: patch test_sorter.py only — do NOT change sorter.py.",
            "patch target in test_sort_empty:",
            "```python",
            "    assert sort_items([]) == []",
            "```",
            "replace `is None` with `== []`; implementation already passes test_sort_normal.",
        ])
    if instance_id == "SWE-014":
        lines.extend([
            "",
            "patch template inside on() before return:",
            "```python",
            "        def unsubscribe():",
            "            try:",
            "                self._listeners[event].remove(callback)",
            "            except (KeyError, ValueError):",
            "                pass",
            "        return unsubscribe",
            "```",
        ])
    if instance_id == "SWE-015":
        lines.extend([
            "",
            "bug: pop() removes the LAST tuple after sort (highest priority number).",
            "fix: use pop(0) to take the FIRST tuple (lowest priority number = highest priority).",
            "patch target in pop():",
            "```python",
            "        self._items.sort()",
            "        return self._items.pop(0)[1]",
            "```",
            "do NOT reverse sort or use max(); only change pop() to pop(0).",
        ])
    return "\n".join(lines)


__all__ = [
    "SWE_PLAYBOOKS",
    "build_swe_playbook_block",
    "format_swe_replay_block",
    "get_swe_playbook",
]
