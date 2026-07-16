#!/usr/bin/env python3
"""Hugging Face Dataset Importer for WFXM Knowledge Warehouse.

Downloads coding trajectory datasets from Hugging Face and converts them
into knowledge files for the WFXM experience system.

Supported datasets:
- choucsan/mimo-claude-code-traces-1k (MCCT-1K): 1017 Claude Code agent trajectories
- nuprl/AgentPack: 1.3M code edits co-authored by agents and humans
- HuggingFaceH4/CodeFeedback-Filtered: Multi-turn coding feedback

Usage:
    python -m butler.memory.knowledge_warehouse.hf_importer --dataset choucsan/mimo-claude-code-traces-1k --limit 200
    python -m butler.memory.knowledge_warehouse.hf_importer --dataset nuprl/AgentPack --limit 100
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HFDataImporter:
    """Import coding trajectory data from Hugging Face datasets."""

    def __init__(self, output_dir: str = ""):
        if not output_dir:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            output_dir = os.path.join(project_root, "knowledge_import", "ai_collected", "code_engineering")
        self._output_dir = output_dir
        os.makedirs(self._output_dir, exist_ok=True)

    def import_mcct_1k(self, limit: int = 200) -> int:
        """Import MCCT-1K dataset (Claude Code agent trajectories).
        
        Dataset: choucsan/mimo-claude-code-traces-1k
        Contains: 1017 complete coding agent trajectories with tool calls, reasoning, and file edits
        """
        try:
            from datasets import load_dataset
        except ImportError:
            logger.error("datasets library not installed. Install with: pip install datasets")
            return 0

        logger.info("Loading MCCT-1K dataset...")
        dataset = load_dataset("choucsan/mimo-claude-code-traces-1k", split="train", streaming=True)
        
        count = 0
        skipped = 0
        
        for i, item in enumerate(dataset):
            if count >= limit:
                break
            
            try:
                md_content = self._mcct_item_to_markdown(item)
                filename = f"mcct_{i:04d}_{self._sanitize_filename(item.get('task', 'untitled'))}.md"
                self._write_file(filename, md_content)
                count += 1
            except Exception as e:
                logger.warning("Skipping item %d: %s", i, e)
                skipped += 1
        
        logger.info("MCCT-1K import completed: %d imported, %d skipped", count, skipped)
        return count

    def import_agentpack(self, limit: int = 100) -> int:
        """Import AgentPack dataset (agent-human co-authored code edits).
        
        Dataset: nuprl/AgentPack
        Contains: 1.3M code edits from Claude Code, Codex, and Cursor Agent
        """
        try:
            from datasets import load_dataset
        except ImportError:
            logger.error("datasets library not installed. Install with: pip install datasets")
            return 0

        logger.info("Loading AgentPack dataset...")
        dataset = load_dataset("nuprl/AgentPack", split="train", streaming=True)
        
        count = 0
        skipped = 0
        
        for i, item in enumerate(dataset):
            if count >= limit:
                break
            
            try:
                md_content = self._agentpack_item_to_markdown(item)
                if md_content:
                    filename = f"agentpack_{i:04d}.md"
                    self._write_file(filename, md_content)
                    count += 1
            except Exception as e:
                logger.warning("Skipping item %d: %s", i, e)
                skipped += 1
        
        logger.info("AgentPack import completed: %d imported, %d skipped", count, skipped)
        return count

    def import_code_feedback(self, limit: int = 200) -> int:
        """Import CodeFeedback dataset (multi-turn coding feedback).
        
        Dataset: HuggingFaceH4/CodeFeedback-Filtered
        Contains: Multi-turn coding conversations with feedback
        """
        try:
            from datasets import load_dataset
        except ImportError:
            logger.error("datasets library not installed. Install with: pip install datasets")
            return 0

        logger.info("Loading CodeFeedback dataset...")
        dataset = load_dataset("HuggingFaceH4/CodeFeedback-Filtered", split="train", streaming=True)
        
        count = 0
        skipped = 0
        
        for i, item in enumerate(dataset):
            if count >= limit:
                break
            
            try:
                md_content = self._code_feedback_item_to_markdown(item)
                filename = f"codefeedback_{i:04d}.md"
                self._write_file(filename, md_content)
                count += 1
            except Exception as e:
                logger.warning("Skipping item %d: %s", i, e)
                skipped += 1
        
        logger.info("CodeFeedback import completed: %d imported, %d skipped", count, skipped)
        return count

    def _mcct_item_to_markdown(self, item: Dict[str, Any]) -> str:
        """Convert MCCT-1K item to markdown format."""
        prompt = item.get("prompt", "")
        messages = item.get("messages", [])
        metadata = item.get("metadata", {})
        trace = item.get("trace", [])
        tools = item.get("tools", [])
        
        md = []
        
        md.append(f"# {prompt[:100]}")
        
        if metadata:
            model = metadata.get("model", "")
            model_provider = metadata.get("model_provider", "")
            cwd = metadata.get("cwd", "")
            if model:
                md.append(f"**Model**: {model_provider} {model}")
            if cwd:
                md.append(f"**Working Directory**: {cwd}")
        md.append("")
        
        md.append("## Task Description")
        md.append(prompt)
        md.append("")
        
        if messages:
            md.append("## Conversation")
            for j, msg in enumerate(messages[:20], 1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])
                tool_results = msg.get("tool_results", [])
                
                md.append(f"### Turn {j} ({role})")
                
                if content:
                    md.append(content)
                
                if tool_calls:
                    for tc in tool_calls:
                        func_name = tc.get("function", {}).get("name", "")
                        func_args = tc.get("function", {}).get("arguments", {})
                        md.append(f"**Tool**: `{func_name}`")
                        if func_args:
                            md.append(f"```json")
                            md.append(json.dumps(func_args, indent=2, ensure_ascii=False)[:500])
                            md.append(f"```")
                
                if tool_results:
                    for tr in tool_results[:2]:
                        result_str = str(tr).replace("\n", "\n> ")[:800]
                        md.append(f"**Tool Result**:")
                        md.append(f"> {result_str}")
                
                md.append("")
        
        if tools:
            md.append("## Available Tools")
            for tool in tools[:10]:
                tool_name = tool.get("function", {}).get("name", "")
                tool_desc = tool.get("function", {}).get("description", "")
                md.append(f"- **{tool_name}**: {tool_desc[:150]}")
            md.append("")
        
        if trace:
            md.append("## Execution Trace")
            tool_events = [t for t in trace if t.get("type") in ("tool-call", "tool-result", "edit", "read")]
            for j, event in enumerate(tool_events[:20], 1):
                event_type = event.get("type", "unknown")
                md.append(f"### Event {j}: {event_type}")
                if "name" in event:
                    md.append(f"- **Name**: {event['name']}")
                if "content" in event:
                    md.append(f"- **Content**: {str(event['content'])[:300]}")
                if "path" in event:
                    md.append(f"- **Path**: {event['path']}")
                md.append("")
        
        return "\n".join(md)

    def _agentpack_item_to_markdown(self, item: Dict[str, Any]) -> str:
        """Convert AgentPack item to markdown format."""
        message = item.get("message", "")
        diff = item.get("diff", "")
        filename = item.get("filename", "")
        agent = item.get("agent", "")
        
        if not message or not diff:
            return ""
        
        md = []
        
        md.append(f"# {message[:80]}")
        if agent:
            md.append(f"**Agent**: {agent}")
        if filename:
            md.append(f"**File**: {filename}")
        md.append("")
        
        md.append("## Commit Message")
        md.append(message)
        md.append("")
        
        md.append("## Code Changes")
        md.append(f"```diff")
        md.append(diff[:2000])
        md.append(f"```")
        
        return "\n".join(md)

    def _code_feedback_item_to_markdown(self, item: Dict[str, Any]) -> str:
        """Convert CodeFeedback item to markdown format."""
        prompt = item.get("prompt", "")
        response = item.get("response", "")
        feedback = item.get("feedback", "")
        corrected_response = item.get("corrected_response", "")
        
        md = []
        
        md.append(f"# {prompt[:80]}")
        md.append("")
        
        md.append("## User Prompt")
        md.append(prompt)
        md.append("")
        
        md.append("## Initial Response")
        md.append(response[:1000])
        md.append("")
        
        if feedback:
            md.append("## Feedback")
            md.append(feedback)
            md.append("")
        
        if corrected_response:
            md.append("## Corrected Response")
            md.append(corrected_response[:1000])
        
        return "\n".join(md)

    def _sanitize_filename(self, text: str) -> str:
        """Sanitize text for use as filename."""
        text = text.replace("/", "_").replace("\\", "_")
        text = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", text)
        return text[:50]

    def _write_file(self, filename: str, content: str) -> None:
        """Write content to file."""
        filepath = os.path.join(self._output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug("Written: %s", filename)


    def import_open_swe_traces(self, limit: int = 200) -> int:
        """Import Open-SWE-Traces dataset (NVIDIA's multilingual agent trajectories).
        
        Dataset: nvidia/open-swe-traces
        Contains: 207K agentic trajectories from real GitHub PRs across 9 languages
        Includes: thinking/non-thinking modes, tool calls, reasoning processes
        """
        try:
            from datasets import load_dataset
        except ImportError:
            logger.error("datasets library not installed. Install with: pip install datasets")
            return 0

        logger.info("Loading Open-SWE-Traces dataset (openhands config)...")
        dataset = load_dataset("nvidia/open-swe-traces", "openhands", split="minimax_m25", streaming=True)
        
        count = 0
        skipped = 0
        
        for i, item in enumerate(dataset):
            if count >= limit:
                break
            
            try:
                md_content = self._open_swe_traces_item_to_markdown(item)
                if md_content:
                    filename = f"openswetraces_{i:04d}.md"
                    self._write_file(filename, md_content)
                    count += 1
            except Exception as e:
                logger.warning("Skipping item %d: %s", i, e)
                skipped += 1
        
        logger.info("Open-SWE-Traces import completed: %d imported, %d skipped", count, skipped)
        return count

    def import_jupyter_agent(self, limit: int = 200) -> int:
        """Import Jupyter Agent Dataset (data science execution traces).
        
        Dataset: jupyter-agent/jupyter-agent-dataset
        Contains: 51K synthetic notebooks with execution traces for data analysis
        """
        try:
            from datasets import load_dataset
        except ImportError:
            logger.error("datasets library not installed. Install with: pip install datasets")
            return 0

        logger.info("Loading Jupyter Agent Dataset...")
        dataset = load_dataset("jupyter-agent/jupyter-agent-dataset", split="thinking", streaming=True)
        
        count = 0
        skipped = 0
        
        for i, item in enumerate(dataset):
            if count >= limit:
                break
            
            try:
                md_content = self._jupyter_agent_item_to_markdown(item)
                if md_content:
                    filename = f"jupyter_{i:04d}.md"
                    self._write_file(filename, md_content)
                    count += 1
            except Exception as e:
                logger.warning("Skipping item %d: %s", i, e)
                skipped += 1
        
        logger.info("Jupyter Agent Dataset import completed: %d imported, %d skipped", count, skipped)
        return count

    def _open_swe_traces_item_to_markdown(self, item: Dict[str, Any]) -> str:
        """Convert Open-SWE-Traces item to markdown format."""
        instance_id = item.get("instance_id", "")
        repo = item.get("repo", "")
        language = item.get("language", "")
        trajectory = item.get("trajectory", [])
        tools = item.get("tools", [])
        resolved = item.get("resolved", False)
        
        if not trajectory:
            return ""
        
        md = []
        
        first_user_msg = ""
        for step in trajectory:
            if step.get("role") == "user":
                first_user_msg = step.get("content", "")[:100]
                break
        
        md.append(f"# {first_user_msg if first_user_msg else instance_id[:50]}")
        
        if repo:
            md.append(f"**Repository**: {repo}")
        if language:
            md.append(f"**Language**: {language}")
        md.append(f"**Resolved**: {'Yes' if resolved else 'No'}")
        md.append("")
        
        md.append("## Execution Trajectory")
        tool_call_count = 0
        
        for j, step in enumerate(trajectory[:30], 1):
            role = step.get("role", "unknown")
            content = step.get("content", "")
            reasoning = step.get("reasoning_content", "") or step.get("think", "")
            tool_calls = step.get("tool_calls", [])
            
            md.append(f"### Step {j} ({role})")
            
            if reasoning:
                md.append(f"**Thinking**: {reasoning[:500]}")
                md.append("")
            
            if content:
                md.append(content[:1000])
                md.append("")
            
            if tool_calls and isinstance(tool_calls, list):
                tool_call_count += len(tool_calls)
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    func_info = tc.get("function", {})
                    if not isinstance(func_info, dict):
                        continue
                    func_name = func_info.get("name", "")
                    func_args_raw = func_info.get("arguments", "")
                    md.append(f"**Tool**: `{func_name}`")
                    if func_args_raw:
                        try:
                            if isinstance(func_args_raw, str):
                                func_args = json.loads(func_args_raw)
                            else:
                                func_args = func_args_raw
                            md.append(f"```json")
                            md.append(json.dumps(func_args, indent=2, ensure_ascii=False)[:500])
                            md.append(f"```")
                        except (json.JSONDecodeError, TypeError):
                            md.append(f"`{func_args_raw[:200]}`")
                md.append("")
        
        md.append(f"**Total Tool Calls**: {tool_call_count}")
        md.append("")
        
        if tools:
            md.append("## Available Tools")
            for tool in tools[:5]:
                tool_name = tool.get("function", {}).get("name", "")
                tool_desc = tool.get("function", {}).get("description", "")
                md.append(f"- **{tool_name}**: {tool_desc[:150]}")
        
        return "\n".join(md)

    def _jupyter_agent_item_to_markdown(self, item: Dict[str, Any]) -> str:
        """Convert Jupyter Agent Dataset item to markdown format."""
        question = item.get("question", "")
        answer = item.get("answer", "")
        messages = item.get("messages", [])
        files_used = item.get("files_used", [])
        packages_used = item.get("packages_used", [])
        
        if not question:
            return ""
        
        md = []
        
        md.append(f"# {question[:100]}")
        
        if files_used:
            md.append(f"**Files Used**: {', '.join(files_used[:5])}")
        if packages_used:
            md.append(f"**Packages Used**: {', '.join(packages_used[:5])}")
        md.append("")
        
        md.append("## Question")
        md.append(question)
        md.append("")
        
        if answer:
            md.append("## Answer")
            md.append(answer)
            md.append("")
        
        if messages:
            md.append("## Execution Trace")
            for j, msg in enumerate(messages[:15], 1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                
                if role == "user":
                    md.append(f"### User Query")
                elif role == "assistant":
                    md.append(f"### Code Generation")
                elif role == "tool":
                    md.append(f"### Execution Result")
                else:
                    md.append(f"### {role.capitalize()}")
                
                md.append(f"```")
                md.append(content[:1500])
                md.append(f"```")
                md.append("")
        
        return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Import HF datasets to WFXM knowledge warehouse")
    parser.add_argument("--dataset", required=True, choices=[
        "mcct-1k",
        "agentpack",
        "codefeedback",
        "open-swe-traces",
        "jupyter-agent",
        "all"
    ], help="Dataset to import")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of items to import")
    parser.add_argument("--output-dir", default="", help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    importer = HFDataImporter(output_dir=args.output_dir)
    
    total_imported = 0
    
    if args.dataset == "mcct-1k" or args.dataset == "all":
        total_imported += importer.import_mcct_1k(limit=args.limit)
    
    if args.dataset == "agentpack" or args.dataset == "all":
        total_imported += importer.import_agentpack(limit=args.limit)
    
    if args.dataset == "codefeedback" or args.dataset == "all":
        total_imported += importer.import_code_feedback(limit=args.limit)
    
    if args.dataset == "open-swe-traces" or args.dataset == "all":
        total_imported += importer.import_open_swe_traces(limit=args.limit)
    
    if args.dataset == "jupyter-agent" or args.dataset == "all":
        total_imported += importer.import_jupyter_agent(limit=args.limit)
    
    print(f"\n=== Import Completed ===")
    print(f"Total files imported: {total_imported}")
    print(f"Output directory: {importer._output_dir}")
    
    return total_imported


if __name__ == "__main__":
    main()