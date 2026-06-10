"""End-to-end regression tests for Butler v4 detailed design (Sprints 1-3).

Covers: TenantStore engine, PIM tool exposure, reminder tenant domain,
natural language time parsing, outbox field consistency, PII prune policy,
and session cost tracking.
"""

from __future__ import annotations


class TestTenantStoreEngine:
    def test_search_finds_by_substring(self, tmp_path, monkeypatch):
        """TenantStore.search works with substring matching."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "default")
        import butler.config
        butler.config.reload_butler_settings()

        from butler.tools.tenant_store import TenantStore
        store = TenantStore("test_items")
        store.save({"id": "1", "name": "张三", "phone": "13800138000"})
        store.save({"id": "2", "name": "李四", "phone": "13900139000"})

        results = store.search("张")
        assert len(results) == 1
        assert results[0]["name"] == "张三"

    def test_search_with_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "default")
        import butler.config
        butler.config.reload_butler_settings()

        from butler.tools.tenant_store import TenantStore
        store = TenantStore("test_items")
        store.save({"id": "1", "name": "Alice", "notes": "works at Google"})
        store.save({"id": "2", "name": "Bob", "notes": "freelancer"})

        results = store.search("Google", fields=["notes"])
        assert len(results) == 1

    def test_find_by_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "default")
        import butler.config
        butler.config.reload_butler_settings()

        from butler.tools.tenant_store import TenantStore
        store = TenantStore("test_items")
        store.save({"id": "abc123def", "name": "test"})

        result = store.find_by_prefix("abc1")
        assert result is not None
        assert result["id"] == "abc123def"

        result = store.find_by_prefix("xyz")
        assert result is None


class TestPIMToolsExposure:
    def test_all_pim_tools_in_butler_set(self):
        from butler.tools.pim_schema import ALL_PIM_TOOLS
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS
        missing = ALL_PIM_TOOLS - _BUTLER_EXTRA_TOOLS
        assert not missing, f"PIM tools missing from butler set: {missing}"

    def test_pim_tools_not_in_lead_set(self):
        from butler.tools.pim_schema import ALL_PIM_TOOLS
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        leaked = ALL_PIM_TOOLS & _LEAD_EXTRA_TOOLS
        assert not leaked, f"PIM tools leaked to lead set: {leaked}"

    def test_no_write_tools_in_butler(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS
        write_tools = {"write_file", "patch", "delete_file", "terminal", "run_shell", "edit_file"}
        leaked = write_tools & _BUTLER_EXTRA_TOOLS
        assert not leaked

    def test_pim_schema_complete(self):
        from butler.tools.pim_schema import ALL_PIM_TOOLS
        assert len(ALL_PIM_TOOLS) == 26


class TestReminderTenantDomain:
    def test_reminders_dir_is_tenant_scoped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "default")
        import butler.config
        butler.config.reload_butler_settings()

        from butler.tools.reminder import _reminders_dir
        rdir = _reminders_dir()
        assert "tenants" in str(rdir)
        assert "default" in str(rdir)


class TestNaturalLanguageTime:
    def test_parse_tomorrow(self):
        from butler.tools.reminder import parse_due_timestamp
        ts = parse_due_timestamp("明天早上9点")
        assert ts is not None
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8)))
        assert dt.hour == 9

    def test_parse_next_monday(self):
        from butler.tools.reminder import parse_due_timestamp
        ts = parse_due_timestamp("下周一")
        assert ts is not None

    def test_parse_monthly_cron(self):
        from butler.tools.reminder import _parse_cron_schedule
        c = _parse_cron_schedule("每月15号")
        assert c == "0 9 15 * *"

    def test_parse_dynamic_monthly(self):
        from butler.tools.reminder import _parse_cron_schedule
        c = _parse_cron_schedule("每月3号")
        assert c == "0 9 3 * *"


class TestOutboxFieldConsistency:
    def test_replay_uses_correct_fields(self):
        import inspect
        from butler.gateway.runner import _replay_pending_outbox
        src = inspect.getsource(_replay_pending_outbox)
        assert 'get("body"' in src, "Replay should read 'body' field"
        assert 'get("entry_id"' in src, "Replay should read 'entry_id' field"


class TestPIIPrunePolicy:
    def test_pim_tools_classified_as_pii_clearable(self):
        from butler.core.tool_prune_policy import classify_tool
        assert classify_tool("contact_find") == "pii_clearable"
        assert classify_tool("memo_search") == "pii_clearable"
        assert classify_tool("expense_list") == "pii_clearable"
        assert classify_tool("habit_stats") == "pii_clearable"

    def test_pim_prune_more_aggressive(self):
        from butler.core.tool_prune_policy import (
            keep_recent_tool_messages,
            keep_recent_pim_tool_messages,
        )
        assert keep_recent_pim_tool_messages() < keep_recent_tool_messages()

    def test_pii_prune_limit_tighter(self):
        from butler.core.tool_prune_policy import prune_limit_chars
        assert prune_limit_chars("pii_clearable") < prune_limit_chars("clearable")


class TestCostTracker:
    def test_cost_tracker_records(self):
        from butler.ops.cost_tracker import SessionCost
        c = SessionCost(session_key="test")
        c.record_llm_call(input_tokens=1000, output_tokens=500)
        c.record_tool_call("memo_add")
        c.record_tool_call("delegate_task")
        c.record_tool_call("read_file")
        assert c.llm_calls == 1
        assert c.total_tokens == 1500
        assert c.tool_calls_pim == 1
        assert c.delegate_spawns == 1
        assert c.tool_calls_other == 1
        summary = c.format_summary()
        assert "1,500" in summary
