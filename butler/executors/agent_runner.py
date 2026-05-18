"""Universal Agent Runner - runs a full agent loop with any model and tool set.

Replaces both ClaudeCodeExecutor and LightAgentExecutor with a single,
model-agnostic agent loop that works with any LLM provider.

v3: Structured AgentReport for multi-granularity information return.
v4: Parallel tool execution, loop detection guardrails, streaming support.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from butler.agent.tool_guardrails import (
    ToolCallGuardrailController,
    append_guidance,
    classify_tool_failure,
    synthetic_result,
)
from butler.agent.subdirectory_hints import SubdirectoryHintTracker
from butler.config.settings import ModelConfig
from butler.providers.base import CompletionResult, LLMProvider, Message
from butler.providers.registry import get_provider_for_model
from butler.tools.output_limits import truncate_output
from butler.tools.schema_sanitizer import sanitize_tool_schemas
from butler.tools.registry import tool_registry
from butler.agent.tool_call_repair import repair_json, build_retry_prompt, validate_tool_call

logger = logging.getLogger(__name__)

MILESTONE_TOOLS = {"write_file", "edit_file", "patch", "git_commit", "run_shell"}

PARALLELIZABLE_TOOLS = {
    "read_file", "search_code", "list_directory",
    "git_status", "git_diff", "git_log", "git_branch",
}


@dataclass
class Change:
    file: str
    action: str  # "created" | "modified" | "deleted"
    description: str


@dataclass
class AgentReport:
    """Multi-granularity structured report from agent execution."""
    headline: str = ""
    changes: list[Change] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"headline": self.headline}
        if self.changes:
            d["changes"] = [{"file": c.file, "action": c.action, "description": c.description} for c in self.changes]
        if self.decisions:
            d["decisions"] = self.decisions
        if self.issues:
            d["issues"] = self.issues
        if self.summary:
            d["summary"] = self.summary
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentReport:
        changes = []
        for c in data.get("changes", []):
            if isinstance(c, dict):
                changes.append(Change(file=c.get("file", ""), action=c.get("action", ""), description=c.get("description", "")))
        return cls(
            headline=data.get("headline", ""),
            changes=changes,
            decisions=data.get("decisions", []),
            issues=data.get("issues", []),
            summary=data.get("summary", ""),
        )


@dataclass
class AgentResult:
    success: bool = True
    response: str = ""
    report: AgentReport = field(default_factory=AgentReport)
    artifacts: list[str] = field(default_factory=list)
    turns_used: int = 0
    tokens_used: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    milestones: list[str] = field(default_factory=list)
    error: str = ""
    stopped_by_guardrail: bool = False


_REPORT_FORMAT_INSTRUCTION = """

## 回复格式要求

当你完成所有工具操作后，最终回复必须包含一个 JSON 块（用 ```json 包裹），格式如下：

```json
{
  "headline": "一句话总结（<=50字）",
  "changes": [
    {"file": "文件路径", "action": "created|modified|deleted", "description": "一句话说明"}
  ],
  "decisions": ["关键决策1及原因", "关键决策2及原因"],
  "issues": ["需要用户关注的问题/风险"],
  "summary": "2-3段落的详细总结，包含做了什么、为什么、效果如何"
}
```

规则：
- headline 必须有，是给用户的一句话摘要
- changes 列出所有文件操作
- decisions 仅列出重要的技术/方案决策，无则留空数组
- issues 列出需要用户关注的风险或未解决问题，无则留空数组
- summary 是完整的过程描述，供用户需要时查看"""


class AgentRunner:
    """Universal agent loop: messages -> LLM -> tool calls -> repeat.

    v4 features:
    - Parallel tool execution for read-only operations
    - Loop detection guardrails
    - Streaming support via on_token callback
    """

    def __init__(
        self,
        model_config: ModelConfig,
        tools: list[str],
        system_prompt: str,
        max_turns: int = 30,
        enable_guardrails: bool = True,
        working_dir: str | None = None,
        sanitize_schemas: bool = True,
    ):
        self.model_config = model_config
        self.tool_names = set(tools)
        self.system_prompt = system_prompt + _REPORT_FORMAT_INSTRUCTION
        self.max_turns = max_turns
        self.guardrails = ToolCallGuardrailController() if enable_guardrails else None
        self.hint_tracker = SubdirectoryHintTracker(working_dir)
        self._sanitize_schemas = sanitize_schemas

    async def run(
        self,
        task: str,
        context: str = "",
        on_turn: Callable[[int, str, str], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """Execute a task through the full agent loop.

        Args:
            task: The task description.
            context: Optional project context (memory, architecture, etc.)
            on_turn: Callback(turn_number, tool_name, brief_output) for progress.
            on_token: Callback(token) for streaming LLM output to caller.

        Returns:
            AgentResult with the final response, structured report, and metadata.
        """
        provider = get_provider_for_model(self.model_config)
        tool_defs = tool_registry.get_definitions(self.tool_names or None)
        if self._sanitize_schemas and tool_defs:
            tool_defs = sanitize_tool_schemas(tool_defs)

        messages: list[Message] = [Message.system(self.system_prompt)]
        if context:
            messages.append(Message.user(f"项目上下文:\n\n{context}"))
        messages.append(Message.user(task))

        total_input = 0
        total_output = 0
        artifacts: list[str] = []
        milestones: list[str] = []

        for turn in range(self.max_turns):
            if self.guardrails:
                self.guardrails.reset_for_turn()
            try:
                if on_token and hasattr(provider, 'complete_stream'):
                    result = await self._stream_completion(
                        provider, messages, tool_defs, on_token
                    )
                else:
                    result = await provider.complete(
                        messages,
                        tools=tool_defs if tool_defs else None,
                        model=self.model_config.model or None,
                        temperature=self.model_config.temperature,
                        max_tokens=self.model_config.max_tokens,
                    )
            except Exception as e:
                logger.error(f"Agent LLM call failed on turn {turn}: {e}")
                return AgentResult(
                    success=False, error=str(e),
                    turns_used=turn, tokens_used={"input": total_input, "output": total_output},
                    milestones=milestones,
                )

            total_input += result.usage.get("input_tokens", 0)
            total_output += result.usage.get("output_tokens", 0)
            messages.append(result.message)

            # Tool call repair for malformed outputs
            if result.message.tool_calls:
                repaired_calls = []
                needs_retry = False
                for tc in result.message.tool_calls:
                    if not isinstance(tc.arguments, dict):
                        repaired = repair_json(str(tc.arguments)) if tc.arguments else None
                        if repaired:
                            tc.arguments = repaired
                            repaired_calls.append(tc)
                        else:
                            needs_retry = True
                            retry_msg = build_retry_prompt(tc.name, "JSON 解析失败", None)
                            messages.append(Message.user(retry_msg))
                            break
                    else:
                        repaired_calls.append(tc)

                if needs_retry:
                    continue  # retry the turn
                result.message.tool_calls = repaired_calls

            if not result.message.tool_calls:
                report = parse_report_from_response(result.message.content, artifacts)
                return AgentResult(
                    success=True,
                    response=result.message.content,
                    report=report,
                    artifacts=artifacts,
                    turns_used=turn + 1,
                    tokens_used={"input": total_input, "output": total_output},
                    milestones=milestones,
                )

            tool_results = await self._execute_tools(
                result.message.tool_calls, artifacts, milestones, turn, on_turn
            )

            for tc, output in tool_results:
                messages.append(Message.tool(tc.id, output))

            # Inject reflection periodically
            if self._should_reflect(turn):
                reflection = self._build_reflection_message(turn, milestones)
                messages.append(Message.user(reflection))

            if (
                self.guardrails
                and self.guardrails.halt_decision is not None
                and self.guardrails.halt_decision.should_halt
            ):
                halt = self.guardrails.halt_decision
                report = parse_report_from_response("", artifacts)
                msg = halt.message or "Guardrail stop"
                report.issues.append(msg)
                return AgentResult(
                    success=False,
                    response=msg,
                    report=report,
                    artifacts=artifacts,
                    turns_used=turn + 1,
                    tokens_used={"input": total_input, "output": total_output},
                    milestones=milestones,
                    stopped_by_guardrail=True,
                )

        report = parse_report_from_response(
            messages[-1].content if messages else "", artifacts
        )
        return AgentResult(
            success=True,
            response=messages[-1].content if messages else "达到最大轮次",
            report=report,
            artifacts=artifacts,
            turns_used=self.max_turns,
            tokens_used={"input": total_input, "output": total_output},
            milestones=milestones,
        )

    async def run_planned(
        self,
        task: str,
        context: str = "",
        on_turn: Callable[[int, str, str], None] | None = None,
        on_token: Callable[[str], None] | None = None,
        max_plan_steps: int = 20,
    ) -> AgentResult:
        """Plan-then-Execute mode: first generate a plan, then execute step by step.

        Better for complex tasks (>10 steps). The agent first produces a numbered
        plan without calling any tools, then executes each step sequentially.
        """
        _ = on_token  # Streaming not used in planned mode; retained for API parity.
        provider = get_provider_for_model(self.model_config)
        tool_defs = tool_registry.get_definitions(self.tool_names or None)
        if self._sanitize_schemas and tool_defs:
            tool_defs = sanitize_tool_schemas(tool_defs)

        # Phase 1: Planning (no tools)
        plan_prompt = (
            f"{task}\n\n"
            "请先制定一个详细的执行计划，列出具体步骤（编号列表）。\n"
            "此阶段只需要输出计划，不要调用任何工具。\n"
            "计划格式：\n"
            "1. [步骤描述]\n"
            "2. [步骤描述]\n"
            "...\n"
            "计划完成后，输出 '---PLAN_READY---' 标记。\n"
            f"步骤数量不要超过 {max_plan_steps} 条。"
        )

        messages: list[Message] = [Message.system(self.system_prompt)]
        if context:
            messages.append(Message.user(f"项目上下文:\n\n{context}"))
        messages.append(Message.user(plan_prompt))

        total_input = 0
        total_output = 0
        artifacts: list[str] = []
        milestones: list[str] = []

        # Get plan from LLM (no tools provided)
        try:
            plan_result = await provider.complete(
                messages,
                tools=None,  # No tools during planning
                model=self.model_config.model or None,
                temperature=self.model_config.temperature,
                max_tokens=self.model_config.max_tokens,
            )
        except Exception as e:
            return AgentResult(success=False, error=f"Planning failed: {e}")

        total_input += plan_result.usage.get("input_tokens", 0)
        total_output += plan_result.usage.get("output_tokens", 0)
        messages.append(plan_result.message)
        milestones.append(f"[计划] 生成了执行计划")

        # Phase 2: Execution (with tools)
        exec_prompt = (
            "计划已制定完成。现在开始按照计划逐步执行。\n"
            "请按照计划中的步骤顺序，使用工具完成每个步骤。\n"
            "每完成一个步骤后，简要说明完成情况，然后继续下一步。"
        )
        messages.append(Message.user(exec_prompt))

        # Now run the standard agent loop with tools
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3
        for turn in range(self.max_turns):
            if self.guardrails:
                self.guardrails.reset_for_turn()
            try:
                result = await provider.complete(
                    messages,
                    tools=tool_defs if tool_defs else None,
                    model=self.model_config.model or None,
                    temperature=self.model_config.temperature,
                    max_tokens=self.model_config.max_tokens,
                )
            except Exception as e:
                return AgentResult(
                    success=False, error=str(e),
                    turns_used=turn, tokens_used={"input": total_input, "output": total_output},
                    milestones=milestones,
                )

            total_input += result.usage.get("input_tokens", 0)
            total_output += result.usage.get("output_tokens", 0)
            messages.append(result.message)

            # Tool call repair for malformed outputs
            if result.message.tool_calls:
                repaired_calls = []
                needs_retry = False
                for tc in result.message.tool_calls:
                    if not isinstance(tc.arguments, dict):
                        repaired = repair_json(str(tc.arguments)) if tc.arguments else None
                        if repaired:
                            tc.arguments = repaired
                            repaired_calls.append(tc)
                        else:
                            needs_retry = True
                            retry_msg = build_retry_prompt(tc.name, "JSON 解析失败", None)
                            messages.append(Message.user(retry_msg))
                            break
                    else:
                        repaired_calls.append(tc)

                if needs_retry:
                    continue  # retry the turn
                result.message.tool_calls = repaired_calls

            if not result.message.tool_calls:
                report = parse_report_from_response(result.message.content, artifacts)
                return AgentResult(
                    success=True,
                    response=result.message.content,
                    report=report,
                    artifacts=artifacts,
                    turns_used=turn + 1,
                    tokens_used={"input": total_input, "output": total_output},
                    milestones=milestones,
                )

            tool_results = await self._execute_tools(
                result.message.tool_calls, artifacts, milestones, turn, on_turn
            )

            for tc, output in tool_results:
                messages.append(Message.tool(tc.id, output))

            # Track failures for dynamic re-planning
            turn_had_failure = any(
                '"error"' in output or '"failed"' in output.lower()
                for _, output in tool_results
            )
            if turn_had_failure:
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            # Dynamic re-planning on consecutive failures
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                replan_msg = (
                    f"[动态重规划] 连续 {consecutive_failures} 轮工具调用出现错误。\n"
                    "请暂停当前执行，重新评估计划：\n"
                    "1. 分析失败原因\n"
                    "2. 调整或修改执行计划\n"
                    "3. 从当前位置继续执行调整后的计划\n"
                    "不要重复之前失败的操作。"
                )
                messages.append(Message.user(replan_msg))
                consecutive_failures = 0
                milestones.append(f"[重规划] 因连续失败触发动态重规划")

            if (self.guardrails and self.guardrails.halt_decision is not None
                    and self.guardrails.halt_decision.should_halt):
                halt = self.guardrails.halt_decision
                report = parse_report_from_response("", artifacts)
                report.issues.append(halt.message or "Guardrail stop")
                return AgentResult(
                    success=False, response=halt.message or "Guardrail stop",
                    report=report, artifacts=artifacts,
                    turns_used=turn + 1,
                    tokens_used={"input": total_input, "output": total_output},
                    milestones=milestones, stopped_by_guardrail=True,
                )

        report = parse_report_from_response(
            messages[-1].content if messages else "", artifacts
        )
        return AgentResult(
            success=True,
            response=messages[-1].content if messages else "达到最大轮次",
            report=report, artifacts=artifacts,
            turns_used=self.max_turns,
            tokens_used={"input": total_input, "output": total_output},
            milestones=milestones,
        )

    def _should_reflect(self, turn: int, interval: int = 8) -> bool:
        return turn > 0 and turn % interval == 0

    def _build_reflection_message(self, turn: int, milestones: list[str]) -> str:
        milestone_text = "\n".join(milestones[-5:]) if milestones else "尚无里程碑"
        return (
            f"[自我反思 - 第{turn}轮]\n"
            f"已完成的步骤:\n{milestone_text}\n\n"
            "请回顾进展：\n"
            "1. 当前任务完成了多少？\n"
            "2. 是否需要调整策略？\n"
            "3. 接下来最重要的步骤是什么？\n"
            "请简要反思后继续执行。"
        )

    async def _execute_tools(
        self,
        tool_calls: list,
        artifacts: list[str],
        milestones: list[str],
        turn: int,
        on_turn: Callable | None,
    ) -> list[tuple[Any, str]]:
        """Execute tool calls, parallelizing read-only operations."""
        all_parallel = all(tc.name in PARALLELIZABLE_TOOLS for tc in tool_calls)

        if all_parallel and len(tool_calls) > 1 and not self.guardrails:
            return await self._execute_parallel(tool_calls, artifacts, milestones, turn, on_turn)
        else:
            return await self._execute_sequential(tool_calls, artifacts, milestones, turn, on_turn)

    async def _execute_parallel(
        self, tool_calls, artifacts, milestones, turn, on_turn
    ) -> list[tuple[Any, str]]:
        """Execute read-only tool calls in parallel."""

        async def _run_one(tc):
            logger.info(f"[Agent turn {turn}] (parallel) {tc.name}({list(tc.arguments.keys())})")
            output = await tool_registry.dispatch(tc.name, tc.arguments)
            return tc, output

        tasks = [_run_one(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs: list[tuple[Any, str]] = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Parallel tool execution error: {r}")
                outputs.append((tool_calls[len(outputs)], json.dumps({"error": str(r)})))
            else:
                tc, output = r
                outputs.append((tc, output))
                if on_turn:
                    brief = output[:150].replace("\n", " ")
                    on_turn(turn, tc.name, brief)

        return outputs

    async def _execute_sequential(
        self, tool_calls, artifacts, milestones, turn, on_turn
    ) -> list[tuple[Any, str]]:
        """Execute tool calls sequentially (for write operations or mixed batches)."""
        results: list[tuple[Any, str]] = []

        for tc in tool_calls:
            logger.info(f"[Agent turn {turn}] {tc.name}({list(tc.arguments.keys())})")

            if self.guardrails:
                pre = self.guardrails.before_call(tc.name, tc.arguments)
                if not pre.allows_execution:
                    output = append_guidance(synthetic_result(pre), pre)
                    results.append((tc, output))
                    if pre.should_halt:
                        logger.warning(f"Guardrail blocked call: {pre.message}")
                        if on_turn:
                            brief = output[:150].replace("\n", " ")
                            on_turn(turn, tc.name, brief)
                        break
                    if on_turn:
                        brief = output[:150].replace("\n", " ")
                        on_turn(turn, tc.name, brief)
                    continue

            output = await tool_registry.dispatch(tc.name, tc.arguments)

            hint = self.hint_tracker.check_tool_call(tc.name, tc.arguments or {})
            if hint:
                output = output + "\n\n" + hint

            if self.guardrails:
                failed, _ = classify_tool_failure(tc.name, output)
                post = self.guardrails.after_call(
                    tc.name, tc.arguments, output, failed=failed
                )
                output = append_guidance(output, post)
                if post.action == "warn" and post.message:
                    logger.warning(f"Guardrail warning: {post.message}")

            results.append((tc, output))

            if tc.name in ("write_file", "edit_file") and "path" in tc.arguments:
                artifacts.append(tc.arguments["path"])

            if tc.name in MILESTONE_TOOLS:
                desc = _milestone_description(tc.name, tc.arguments, output)
                milestones.append(f"[步骤{len(milestones)+1}] {desc}")

            if self.guardrails and (
                self.guardrails.halt_decision is not None
                and self.guardrails.halt_decision.should_halt
            ):
                if on_turn:
                    brief = output[:150].replace("\n", " ")
                    on_turn(turn, tc.name, brief)
                break

            if on_turn:
                brief = output[:150].replace("\n", " ")
                on_turn(turn, tc.name, brief)

        return results

    async def _stream_completion(
        self, provider, messages, tool_defs, on_token
    ) -> CompletionResult:
        """Attempt streaming completion if provider supports it."""
        if hasattr(provider, 'complete_stream'):
            try:
                return await provider.complete_stream(
                    messages,
                    tools=tool_defs if tool_defs else None,
                    model=self.model_config.model or None,
                    temperature=self.model_config.temperature,
                    max_tokens=self.model_config.max_tokens,
                    on_token=on_token,
                )
            except (AttributeError, NotImplementedError):
                pass

        return await provider.complete(
            messages,
            tools=tool_defs if tool_defs else None,
            model=self.model_config.model or None,
            temperature=self.model_config.temperature,
            max_tokens=self.model_config.max_tokens,
        )


def parse_report_from_response(response: str, artifacts: list[str] | None = None) -> AgentReport:
    """Extract structured AgentReport from agent's final response."""
    report_data = _extract_json_block(response)
    if report_data:
        return AgentReport.from_dict(report_data)
    return _build_fallback_report(response, artifacts or [])


def _extract_json_block(text: str) -> dict | None:
    """Find and parse a ```json ... ``` block in the text."""
    import re
    pattern = r'```json\s*\n(.*?)\n\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        brace_start = text.rfind('{"headline"')
        if brace_start == -1:
            return None
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i+1])
                    except json.JSONDecodeError:
                        return None
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _build_fallback_report(response: str, artifacts: list[str]) -> AgentReport:
    """Build a minimal report when agent didn't produce structured JSON."""
    lines = response.strip().splitlines()
    headline = lines[0][:80] if lines else "任务完成"

    changes = []
    for path in artifacts:
        changes.append(Change(file=path, action="modified", description=""))

    return AgentReport(
        headline=headline,
        changes=changes,
        summary=response[:2000] if len(response) > 80 else "",
    )


def _milestone_description(tool_name: str, args: dict, output: str) -> str:
    if tool_name == "write_file":
        return f"创建/写入 {args.get('path', '?')}"
    elif tool_name == "edit_file":
        return f"修改 {args.get('path', '?')}"
    elif tool_name == "git_commit":
        return f"Git 提交: {args.get('message', '')[:40]}"
    elif tool_name == "run_shell":
        cmd = args.get("command", "")[:50]
        ok = '"exit_code": 0' in output[:200] or '"error"' not in output[:200]
        status = "成功" if ok else "失败"
        return f"执行命令 ({status}): {cmd}"
    return f"{tool_name}"
