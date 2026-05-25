"""Workflow nodes pass handoff_only from schema."""

from __future__ import annotations

from butler.workflows.schema import parse_step


def test_parse_step_handoff_only_default():
    step = parse_step(
        {
            "id": "a",
            "role": "dev",
            "task": "do thing",
            "depends_on": [],
        }
    )
    assert step is not None
    assert step.handoff_only is True


def test_parse_step_handoff_only_off():
    step = parse_step(
        {
            "id": "a",
            "role": "dev",
            "task": "do thing",
            "handoff_only": False,
        }
    )
    assert step is not None
    assert step.handoff_only is False
