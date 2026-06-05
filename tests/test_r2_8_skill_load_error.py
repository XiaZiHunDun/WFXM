"""R2-8 regression: skill frontmatter load errors must be disambiguated + aggregatable.

Audit (project-deep-audit-2026-06-r1to8 §R2-8):
``butler/skills/manager.py:107-122`` reported 3 distinct failure modes
(no opening ``---``, unterminated frontmatter, invalid UTF-8) with the SAME
warning message, so operators could not tell *why* a skill file failed to
load. The OSError path also used ``logger.warning`` instead of
``logger.error(..., exc_info=exc)``.

Required behavior (this commit):
1. ``SkillLoadError`` exception class exists with ``code``, ``path``, ``message``.
2. A module-level recent-errors buffer is exposed via
   ``recent_skill_load_errors(limit)`` for /诊断 aggregation.
3. ``_read_frontmatter_only`` logs 3 distinct messages + 2 distinct ERROR-level
   messages with ``exc_info``, and appends a categorized ``SkillLoadError`` for
   each failure to the buffer.
4. ``_parse_skill_md`` regex-miss path uses a distinct disambiguated message.
5. Existing public behavior of ``list_skills`` / ``get_skill`` is unchanged.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest

from butler.skills import manager as skills_manager
from butler.skills.manager import (
    SkillLoadError,
    _parse_skill_md,
    _read_frontmatter_only,
    recent_skill_load_errors,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_skill_error_buffer():
    """Reset the module-level error buffer around every test for isolation."""
    skills_manager._clear_recent_skill_load_errors()
    yield
    skills_manager._clear_recent_skill_load_errors()


# ---------------------------------------------------------------------------
# Site 1: 3 distinct log messages for _read_frontmatter_only
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestReadFrontmatterOnlyLogMessages:
    def test_no_frontmatter_log_message_is_distinct(self, caplog, tmp_path: Path):
        """File without leading --- logs the 'no YAML frontmatter opener' code."""
        path = tmp_path / "no-frontmatter.md"
        path.write_text("name: no frontmatter here\nbody line\n", encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            result = _read_frontmatter_only(path)

        assert result is None
        msgs = [r.getMessage() for r in caplog.records]
        assert any("no YAML frontmatter opener" in m for m in msgs), (
            "missing 'no YAML frontmatter opener' log; got messages: "
            f"{msgs}"
        )

        # Buffer must contain a categorized SkillLoadError
        recent = recent_skill_load_errors()
        assert len(recent) == 1
        assert recent[0].code == "no_frontmatter"
        assert recent[0].path == path
        assert "no YAML frontmatter opener" in recent[0].message

    def test_unterminated_frontmatter_log_message_is_distinct(
        self, caplog, tmp_path: Path
    ):
        """File with opening --- but no closing --- logs the unterminated code."""
        path = tmp_path / "unterminated.md"
        path.write_text(
            "---\nname: unterminated\nversion: 1\nbody line\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            result = _read_frontmatter_only(path)

        assert result is None
        msgs = [r.getMessage() for r in caplog.records]
        assert any("unterminated YAML frontmatter" in m for m in msgs), (
            f"missing 'unterminated YAML frontmatter' log; got: {msgs}"
        )
        # MUST NOT use the 'no frontmatter opener' message
        assert not any("no YAML frontmatter opener" in m for m in msgs), (
            "R2-8: unterminated file must NOT be mislabeled as 'no frontmatter opener'; "
            f"got: {msgs}"
        )

        recent = recent_skill_load_errors()
        assert len(recent) == 1
        assert recent[0].code == "unterminated_frontmatter"
        assert recent[0].path == path

    def test_encoding_error_uses_exc_info(self, caplog, tmp_path: Path):
        """Invalid UTF-8 in frontmatter logs at ERROR with exc_info."""
        path = tmp_path / "bad-encoding.md"
        # frontmatter contains \xff\xfe (invalid UTF-8)
        path.write_bytes(
            b"---\nname: bad\nversion: 1\n\xff\xfe\n---\n"
        )

        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            result = _read_frontmatter_only(path)

        assert result is None
        error_records = [
            r
            for r in caplog.records
            if r.name == "butler.skills.manager"
            and r.levelno >= logging.ERROR
            and "invalid UTF-8" in r.getMessage()
        ]
        assert error_records, (
            "R2-8: encoding error must logger.error(..., exc_info=exc); got: "
            f"{[(r.levelname, r.getMessage(), r.exc_info) for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in error_records), (
            "R2-8: encoding error log must include exc_info"
        )

        recent = recent_skill_load_errors()
        assert len(recent) == 1
        assert recent[0].code == "frontmatter_encoding"
        assert recent[0].path == path

    def test_io_error_uses_exc_info(self, caplog, tmp_path: Path):
        """OSError (e.g. file missing) logs at ERROR with exc_info."""
        path = tmp_path / "does-not-exist.md"
        assert not path.exists()

        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            result = _read_frontmatter_only(path)

        assert result is None
        error_records = [
            r
            for r in caplog.records
            if r.name == "butler.skills.manager"
            and r.levelno >= logging.ERROR
            and "could not be opened" in r.getMessage()
        ]
        assert error_records, (
            "R2-8: OSError must logger.error(..., exc_info=exc); got: "
            f"{[(r.levelname, r.getMessage(), r.exc_info) for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in error_records), (
            "R2-8: OSError log must include exc_info"
        )

        recent = recent_skill_load_errors()
        assert len(recent) == 1
        assert recent[0].code == "skill_io_error"
        assert recent[0].path == path


# ---------------------------------------------------------------------------
# Site 2: SkillLoadError exception class
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestSkillLoadErrorClass:
    def test_skill_load_error_class_exists(self):
        assert SkillLoadError is not None
        assert issubclass(SkillLoadError, Exception)

    def test_skill_load_error_instantiation(self, tmp_path: Path):
        path = tmp_path / "x.md"
        err = SkillLoadError(
            code="no_frontmatter",
            path=path,
            message="test message",
        )
        assert err.code == "no_frontmatter"
        assert err.path == path
        assert err.message == "test message"
        # str() yields the message (so it surfaces naturally in tracebacks)
        assert "test message" in str(err)


# ---------------------------------------------------------------------------
# Site 3: recent_skill_load_errors buffer
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestRecentSkillLoadErrorsBuffer:
    def test_recent_skill_load_errors_records_each_error(self, tmp_path: Path):
        # Three distinct error codes via three distinct files
        path1 = tmp_path / "no-fm.md"
        path1.write_text("no frontmatter\n", encoding="utf-8")
        path2 = tmp_path / "unterm.md"
        path2.write_text("---\nname: x\nbody\n", encoding="utf-8")
        path3 = tmp_path / "bad-enc.md"
        path3.write_bytes(b"---\nname: x\n\xff\xfe\n---\n")

        _read_frontmatter_only(path1)
        _read_frontmatter_only(path2)
        _read_frontmatter_only(path3)

        recent = recent_skill_load_errors()
        assert len(recent) == 3
        codes = [e.code for e in recent]
        assert "no_frontmatter" in codes
        assert "unterminated_frontmatter" in codes
        assert "frontmatter_encoding" in codes

    def test_recent_skill_load_errors_respects_limit(self, tmp_path: Path):
        # Generate 5 no-frontmatter errors
        for i in range(5):
            p = tmp_path / f"file-{i}.md"
            p.write_text("no frontmatter\n", encoding="utf-8")
            _read_frontmatter_only(p)

        recent = recent_skill_load_errors(limit=3)
        assert len(recent) == 3

        # No limit returns everything currently recorded
        recent_all = recent_skill_load_errors()
        assert len(recent_all) == 5

    def test_no_duplicate_warning_message_for_unterminated(
        self, caplog, tmp_path: Path
    ):
        """A file with opener but no closer must NOT log the 'no opener' message."""
        path = tmp_path / "u.md"
        path.write_text(
            "---\nname: unterminated\nversion: 1\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            _read_frontmatter_only(path)

        msgs = [r.getMessage() for r in caplog.records]
        assert "no YAML frontmatter opener" not in " | ".join(msgs), (
            "R2-8: unterminated must be disambiguated from 'no opener'; got: "
            f"{msgs}"
        )
        assert any("unterminated YAML frontmatter" in m for m in msgs), (
            f"R2-8: unterminated message missing; got: {msgs}"
        )

    def test_buffer_is_cleared_by_helper(self, tmp_path: Path):
        p = tmp_path / "no-fm.md"
        p.write_text("no frontmatter\n", encoding="utf-8")
        _read_frontmatter_only(p)
        assert len(recent_skill_load_errors()) == 1

        skills_manager._clear_recent_skill_load_errors()
        assert recent_skill_load_errors() == []


# ---------------------------------------------------------------------------
# Site 4: Parametrized code coverage
# ---------------------------------------------------------------------------


@pytest.mark.module_test
@pytest.mark.parametrize(
    "filename,write_bytes,expected_code",
    [
        ("a.md", lambda p: p.write_text("plain text\n", encoding="utf-8"),
         "no_frontmatter"),
        ("b.md", lambda p: p.write_text("---\nname: x\n", encoding="utf-8"),
         "unterminated_frontmatter"),
        ("c.md", lambda p: p.write_bytes(b"---\nname: x\n\xff\xfe\n---\n"),
         "frontmatter_encoding"),
        ("d.md", lambda p: None,  # path is never created => OSError
         "skill_io_error"),
    ],
)
def test_skill_load_error_codes(
    filename, write_bytes, expected_code, tmp_path: Path
):
    path = tmp_path / filename
    write_bytes(path)

    _read_frontmatter_only(path)

    recent = recent_skill_load_errors()
    assert len(recent) == 1, (
        f"expected exactly one recorded error for {filename}, got {len(recent)}"
    )
    assert recent[0].code == expected_code, (
        f"for {filename}: expected code {expected_code!r}, got {recent[0].code!r}"
    )


# ---------------------------------------------------------------------------
# Site 5: _parse_skill_md disambiguation
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestParseSkillMdDisambiguation:
    def test_parse_skill_md_uses_disambiguated_message_for_regex_miss(
        self, caplog, tmp_path: Path
    ):
        """A file that bypasses _read_frontmatter_only but still lacks proper
        frontmatter should log the new 'missing or malformed' message when
        passed through _parse_skill_md."""
        path = tmp_path / "malformed.md"
        # No frontmatter at all: opens with plain text, not '---'
        text = "name: not frontmatter\nbody line\n"
        path.write_text(text, encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            result = _parse_skill_md(text, path, "project")

        assert result is None  # contract unchanged
        msgs = [r.getMessage() for r in caplog.records]
        assert any("missing or malformed YAML frontmatter" in m for m in msgs), (
            f"R2-8 bonus: _parse_skill_md must use distinct disambiguated message; got: {msgs}"
        )


# ---------------------------------------------------------------------------
# Site 6: Regression — happy path still works
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestHappyPathUnchanged:
    def test_valid_frontmatter_returns_string(self, tmp_path: Path):
        path = tmp_path / "valid.md"
        path.write_text(
            "---\nname: valid\nversion: 1\n---\nbody\n",
            encoding="utf-8",
        )
        result = _read_frontmatter_only(path)
        assert result is not None
        assert "name: valid" in result
        # Happy path must not pollute the error buffer
        assert recent_skill_load_errors() == []

    def test_list_skills_with_malformed_file_does_not_raise(self, tmp_path: Path):
        """R2-8 must not break the existing list_skills() contract for files
        with missing/unterminated frontmatter (see existing test
        test_list_skills_reads_frontmatter_without_decoding_body)."""
        from butler.skills.manager import SkillManager

        # Mix: one good, one with no frontmatter, one with unterminated
        (tmp_path / "good.md").write_text(
            "---\nname: good\ndescription: d\ntriggers: [t]\nversion: 1\ncreated: 2026-01-01\n---\nbody\n",
            encoding="utf-8",
        )
        (tmp_path / "bad.md").write_text(
            "no frontmatter here\n",
            encoding="utf-8",
        )
        (tmp_path / "unterm.md").write_text(
            "---\nname: unterm\nbody line\n",
            encoding="utf-8",
        )

        mgr = SkillManager(tmp_path)
        skills = mgr.list_skills()
        # Only the good skill should appear; the others get filtered
        names = [s["name"] for s in skills]
        assert "good" in names
        # The two malformed ones are NOT loaded; not a crash
        assert len(skills) == 1
