"""Lightweight ``until`` assertions on workflow step output."""

from __future__ import annotations

import json
import re
from typing import Any


def evaluate_until(response_text: str, until_spec: dict[str, Any] | None) -> tuple[bool, str]:
    if not until_spec or not isinstance(until_spec, dict):
        return True, ""
    text = str(response_text or "")
    lower = text.lower()

    contains = until_spec.get("output_contains") or until_spec.get("contains")
    if isinstance(contains, str) and contains.strip():
        if contains.lower() not in lower:
            return False, f"until: output missing substring {contains!r}"

    regex = until_spec.get("output_regex") or until_spec.get("regex")
    if isinstance(regex, str) and regex.strip():
        if not re.search(regex, text, re.I | re.DOTALL):
            return False, f"until: output regex not matched"

    rating = until_spec.get("rating") or until_spec.get("decision")
    if rating is not None:
        want = str(rating).strip().lower()
        found = False
        for pat in (
            rf"\b{re.escape(want)}\b",
            rf'"rating"\s*:\s*"{re.escape(want)}"',
            rf'"decision"\s*:\s*"{re.escape(want)}"',
        ):
            if re.search(pat, lower):
                found = True
                break
        if not found:
            try:
                blob = json.loads(text)
                if isinstance(blob, dict):
                    for key in ("rating", "decision", "verdict"):
                        if str(blob.get(key, "")).lower() == want:
                            found = True
                            break
            except json.JSONDecodeError:
                pass
        if not found:
            return False, f"until: expected rating/decision {want!r}"

    min_len = until_spec.get("min_length")
    if min_len is not None:
        try:
            if len(text.strip()) < int(min_len):
                return False, f"until: output shorter than {min_len}"
        except (TypeError, ValueError):
            pass

    return True, ""


__all__ = ["evaluate_until"]
