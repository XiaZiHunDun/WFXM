from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from .schema import FileContainsSpec, ScenarioCase


@dataclass(frozen=True)
class SimRenderContext:
    sim_date: str
    sim_id: str

    @property
    def sim_smoke_file(self) -> str:
        return f"owner-sim-smoke-{self.sim_date}.md"

    @property
    def sim_dev_md(self) -> str:
        return f"dev-delegate-sim-{self.sim_date}.md"

    @property
    def sim_dev_py(self) -> str:
        return f"dev-delegate-sim-{self.sim_id}.py"

    def render(self, text: str) -> str:
        if not text:
            return text
        return (
            text.replace("{sim_smoke_file}", self.sim_smoke_file)
            .replace("{sim_dev_md}", self.sim_dev_md)
            .replace("{sim_dev_py}", self.sim_dev_py)
            .replace("{sim_date}", self.sim_date)
            .replace("{sim_id}", self.sim_id)
        )

    def render_tuple(self, items: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self.render(x) for x in items)


def make_sim_render_context(*, today: date | None = None, run_ns: int | None = None) -> SimRenderContext:
    day = today or date.today()
    ns = run_ns if run_ns is not None else time.time_ns()
    return SimRenderContext(
        sim_date=day.isoformat(),
        sim_id=format(ns % 0xFFFFFF, "06x"),
    )


def _render_file_contains(
    specs: tuple[FileContainsSpec, ...],
    ctx: SimRenderContext,
) -> tuple[FileContainsSpec, ...]:
    out: list[FileContainsSpec] = []
    for spec in specs:
        out.append(
            FileContainsSpec(
                path=ctx.render(spec.path),
                substrings=ctx.render_tuple(spec.substrings),
            )
        )
    return tuple(out)


def render_scenario_case(case: ScenarioCase, ctx: SimRenderContext) -> ScenarioCase:
    return ScenarioCase(
        name=case.name,
        user_text=ctx.render(case.user_text),
        expect_reply_any=ctx.render_tuple(case.expect_reply_any),
        reject_reply_any=ctx.render_tuple(case.reject_reply_any),
        expect_tools_any=case.expect_tools_any,
        prefer_tools_any=case.prefer_tools_any,
        forbid_tools=case.forbid_tools,
        tier=case.tier,
        max_seconds=case.max_seconds,
        requires_mcp=case.requires_mcp,
        skip_in_quick=case.skip_in_quick,
        fresh_session=case.fresh_session,
        soft=case.soft,
        verify_files_exist=ctx.render_tuple(case.verify_files_exist),
        verify_files_missing=ctx.render_tuple(case.verify_files_missing),
        verify_file_contains=_render_file_contains(case.verify_file_contains, ctx),
        prompt_hint=ctx.render(case.prompt_hint),
        require_tools=case.require_tools,
        simulate_wechat_outbound=case.simulate_wechat_outbound,
        expect_outbound_any=ctx.render_tuple(case.expect_outbound_any),
        min_outbound_messages=case.min_outbound_messages,
    )