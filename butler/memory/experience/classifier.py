"""DomainClassifier — classifies new experiences into domain + category.

Used by ExperienceWriter when writing new experiences.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from butler.memory.experience.taxonomy import DOMAINS, CATEGORIES, get_all_domain_keywords

logger = logging.getLogger(__name__)


class DomainClassifier:
    """Classifies a (query, result) pair into (domain_id, category_id)."""

    # Category detection patterns
    CATEGORY_PATTERNS: dict[str, list[str]] = {
        "skills": ["skill", "技能", "react", "map-reduce", "prompt template",
                    "few-shot", "zero-shot", "chain-of-thought"],
        "tools": ["tool", "terminal", "read_file", "write_file", "edit",
                   "grep", "glob", "run_command", "delegate_task",
                   "工具", "调用", "执行"],
        "mcp": ["mcp", "model context protocol", "mcp server", "mcp tool"],
        "workflows": ["workflow", "pipeline", "步骤", "流程", "编排",
                       "step 1", "step 2", "checklist", "工作流"],
        "user_profile": ["偏好", "习惯", "喜欢", "倾向", "preference",
                         "habit", "always uses", "never uses", "用户"],
        "local_products": ["redis", "langfuse", "chromadb", "docker",
                           "postgres", "sqlite", "networkx", "已接入",
                           "已安装", "端口"],
        "recent_conversations": ["刚才", "之前讨论", "上一轮", "recent",
                                  "today", "昨天", "本章", "章节摘要"],
        "knowledge_facts": ["best practice", "最佳实践", "原则", "principle",
                            "fact", "事实", "knowledge", "知识点",
                            "always", "never", "应该", "不应"],
    }

    def classify(
        self,
        query: str,
        result: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, str, float]:
        """Classify into (domain_id, category_id, confidence).

        Returns:
            (domain_id, category_id, confidence) — confidence in [0, 1]
        """
        combined = f"{query} {result} {metadata or ''}".lower()
        meta = metadata or {}

        # Step 1: Domain classification via domain_hint (highest priority)
        domain_hint = meta.get("domain_hint")
        if domain_hint and domain_hint in DOMAINS:
            best_domain = domain_hint
            domain_confidence = 0.95
        else:
            # Step 1a: Domain classification via keyword matching
            domain_scores: dict[str, float] = {}
            keywords_map = get_all_domain_keywords()
            for domain_id, keywords in keywords_map.items():
                score = 0.0
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower in combined:
                        score += 1.0
                if score > 0:
                    domain_scores[domain_id] = score

            if domain_scores:
                best_domain = max(domain_scores, key=domain_scores.get)
                domain_confidence = min(domain_scores[best_domain] / 5.0, 1.0)
            else:
                best_domain = "daily_life"
                domain_confidence = 0.3

        # Step 2: Category classification via pattern matching
        category_scores: dict[str, float] = {}
        for cat_id, patterns in self.CATEGORY_PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                if pattern.lower() in combined:
                    score += 1.0
            if score > 0:
                category_scores[cat_id] = score

        if category_scores:
            best_category = max(category_scores, key=category_scores.get)
        else:
            best_category = "knowledge_facts"

        # Step 3: Override category based on metadata hints
        if metadata:
            if metadata.get("tool_name"):
                best_category = "tools"
            elif metadata.get("skill_name"):
                best_category = "skills"
            elif metadata.get("mcp_name"):
                best_category = "mcp"
            elif metadata.get("workflow_id"):
                best_category = "workflows"
            elif metadata.get("conversation_id"):
                best_category = "recent_conversations"
            elif metadata.get("product_name"):
                best_category = "local_products"

        confidence = round(domain_confidence * 0.7 + 0.3, 4)
        return best_domain, best_category, confidence

    def classify_domain(self, text: str) -> tuple[str, float]:
        """Classify text into a single domain. Returns (domain_id, confidence)."""
        text_lower = text.lower()
        domain_scores: dict[str, float] = {}
        keywords_map = get_all_domain_keywords()
        for domain_id, keywords in keywords_map.items():
            score = sum(1.0 for kw in keywords if kw.lower() in text_lower)
            if score > 0:
                domain_scores[domain_id] = score

        if not domain_scores:
            return "daily_life", 0.2

        best_domain = max(domain_scores, key=domain_scores.get)
        confidence = min(domain_scores[best_domain] / 5.0, 1.0)
        return best_domain, confidence
