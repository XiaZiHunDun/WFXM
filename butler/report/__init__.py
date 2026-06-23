"""Agent report generation, formatting, and persistence."""

from butler.report.generator import (  # noqa: F401
    AgentReport,
    Change,
    build_schema_repair_prompt,
    cache_report,
    clear_report_cache,
    enrich_output_schema,
    enrich_report_decisions,
    attach_delegate_task_times,
    format_detail,
    format_for_butler_tool_result,
    format_for_cli,
    format_for_wechat,
    get_last_report,
    maybe_repair_structured_output,
    parse_decisions_from_text,
    parse_structured_output,
    render_structured_output_markdown,
    validate_structured_output,
)
