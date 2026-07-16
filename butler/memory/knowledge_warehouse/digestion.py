"""DigestionPipeline — transforms raw materials into structured experiences.

Digestion flow:
    queued → digesting → LLM extract → ExperienceWriter.write() → digested
                        ↘ failed ↗
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Any, Optional

from butler.memory.experience.tree import ExperienceTree
from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse

logger = logging.getLogger(__name__)


class DigestionPipeline:
    _DEFAULT_BATCH_SIZE = 5
    _MAX_CONTENT_LENGTH = 4000

    def __init__(
        self,
        warehouse: KnowledgeWarehouse | None = None,
        experience_tree: ExperienceTree | None = None,
    ):
        self._warehouse = warehouse or KnowledgeWarehouse()
        self._experience_tree = experience_tree or ExperienceTree()
        self._kg = None
        try:
            from butler.memory.knowledge_graph import get_knowledge_graph
            self._kg = get_knowledge_graph()
            logger.debug("KnowledgeGraph initialized for digestion")
        except Exception as e:
            logger.debug("KnowledgeGraph not available: %s", e)

    def process_batch(self, batch_size: int | None = None) -> int:
        """Process a batch of queued materials. Returns count processed."""
        batch_size = batch_size or self._DEFAULT_BATCH_SIZE
        queued = self._warehouse.get_queued_materials(limit=batch_size)

        processed = 0
        for material in queued:
            try:
                self._process_material(material)
                processed += 1
            except Exception as e:
                logger.error("Failed to process material %s: %s", material.material_id, e)
                self._warehouse.update_status(material.material_id, "failed", str(e))

        return processed

    def process_all(self) -> int:
        """Process all queued materials. Returns total count processed."""
        total = 0
        while True:
            count = self.process_batch()
            if count == 0:
                break
            total += count
        return total

    def process_single(self, material_id: str) -> bool:
        """Process a single material by ID. Returns success."""
        material = self._warehouse.get_material(material_id)
        if not material:
            logger.error("Material not found: %s", material_id)
            return False

        try:
            self._process_material(material)
            return True
        except Exception as e:
            logger.error("Failed to process material %s: %s", material_id, e)
            self._warehouse.update_status(material_id, "failed", str(e))
            return False

    def _process_material(self, material) -> None:
        self._warehouse.update_status(material.material_id, "digesting")

        content = material.raw_content[:self._MAX_CONTENT_LENGTH]

        experience_ids = []

        extracted = self._extract_knowledge(content, material.domain_hint)
        if extracted:
            for item in extracted:
                meta = {
                    "material_id": material.material_id,
                    "source_type": material.source_type,
                    "extracted_type": item.get("type", "knowledge_fact"),
                    "domain_hint": material.domain_hint,
                }
                if material.source_url:
                    meta["source_url"] = material.source_url
                if material.source_file:
                    meta["source_file"] = material.source_file

                exp_id = self._experience_tree.write(
                    query=item.get("question", item.get("title", "")),
                    result=item.get("answer", item.get("content", "")),
                    metadata=meta,
                )
                experience_ids.append(exp_id)

        self._warehouse.mark_digested(material.material_id, experience_ids)
        logger.info("Digested material %s → %d experiences", material.material_id, len(experience_ids))

        self._extract_entities_to_kg(content, material.domain_hint, experience_ids)

        self._link_related_experiences(experience_ids)

        self._archive_source_file(material)

    def _archive_source_file(self, material) -> None:
        """Move source file from user_uploads to processed/{domain}/ directory."""
        if not material.source_file:
            logger.debug("No source_file for material %s", material.material_id)
            return

        source_file = material.source_file
        logger.debug("Source file: %s", source_file)

        if "user_uploads" not in source_file:
            logger.debug("Not a user_uploads file, skipping archive")
            return

        if not os.path.isabs(source_file):
            source_file = os.path.abspath(source_file)
            logger.debug("Converted to absolute path: %s", source_file)

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        processed_dir = os.path.join(project_root, "knowledge_import", "processed")
        domain = material.domain_hint or "unclassified"
        target_dir = os.path.join(processed_dir, domain)

        try:
            os.makedirs(target_dir, exist_ok=True)
            filename = os.path.basename(source_file)
            target_path = os.path.join(target_dir, filename)

            if os.path.exists(source_file):
                shutil.move(source_file, target_path)
                logger.info("Moved source file to processed: %s -> %s", filename, target_dir)

                new_source_file = target_path
                self._warehouse._update_source_file(material.material_id, new_source_file)
            else:
                logger.warning("Source file not found: %s", source_file)

        except Exception as e:
            logger.error("Failed to archive source file %s: %s", source_file, e)

    def _extract_entities_to_kg(self, content: str, domain_hint: str, experience_ids: list[str]) -> None:
        """Extract entities and relations from content and add to KnowledgeGraph."""
        if not self._kg:
            return

        try:
            tech_patterns = {
                "Python": ["python", "pytest", "django", "flask", "fastapi", "numpy", "pandas"],
                "JavaScript": ["javascript", "typescript", "react", "node", "vue", "webpack"],
                "SQL": ["sql", "postgresql", "mysql", "sqlite", "redis", "mongodb"],
                "DevOps": ["docker", "kubernetes", "ci/cd", "github actions", "prometheus"],
                "LLM": ["llm", "gpt", "claude", "openai", "prompt", "embedding", "token",
                        "transformer", "fine tune", "fine-tune", "fine tuning", "peft", "lora",
                        "attention", "bert", "gpt", "t5", "llama", "mistral", "rag", "rerank"],
                "Agent": ["agent", "tool", "skill", "mcp", "react", "chain"],
                "Security": ["security", "encrypt", "jwt", "oauth", "ssl"],
            }

            entities_found = {}
            for tech_type, keywords in tech_patterns.items():
                for kw in keywords:
                    if kw.lower() in content.lower():
                        entity_id = f"{tech_type.lower()}:{kw}"
                        entities_found[entity_id] = {"label": kw.capitalize(), "type": tech_type}

            for entity_id, info in entities_found.items():
                self._kg.add_entity(entity_id, info["label"], info["type"])

            for exp_id in experience_ids:
                self._kg.add_entity(f"experience:{exp_id}", exp_id, "experience")

            for entity_id in entities_found:
                for exp_id in experience_ids:
                    self._kg.add_relation(f"experience:{exp_id}", "mentions", entity_id)

            for i, exp_id1 in enumerate(experience_ids):
                for j, exp_id2 in enumerate(experience_ids):
                    if i < j:
                        self._kg.add_relation(f"experience:{exp_id1}", "related_to", f"experience:{exp_id2}")

            logger.debug("Added %d entities and relations to KnowledgeGraph", len(entities_found))
        except Exception as e:
            logger.error("Failed to extract entities: %s", e)

    def _link_related_experiences(self, experience_ids: list[str]) -> None:
        """Create cross-links between related experiences."""
        try:
            for i, exp_id1 in enumerate(experience_ids):
                for j, exp_id2 in enumerate(experience_ids):
                    if i < j:
                        self._experience_tree.link_experience(exp_id1, exp_id2, "related_to", 0.8)
            logger.debug("Created %d cross-links between experiences", len(experience_ids) * (len(experience_ids) - 1) // 2)
        except Exception as e:
            logger.error("Failed to link experiences: %s", e)

    def _extract_knowledge(self, content: str, domain_hint: str) -> list[dict[str, str]]:
        """Extract structured knowledge from content using LLM.

        Returns list of {type, question/title, answer/content}
        """
        try:
            from butler.transport.llm import call_llm

            prompt = f"""你是一个知识提取专家。请从以下文本中提取结构化的知识条目。

领域提示: {domain_hint or '通用'}

文本内容:
{content}

要求:
1. 提取 3-10 个知识条目
2. 每个条目包含：类型(skills/tools/workflows/knowledge_facts)、问题/标题、答案/内容
3. 答案要简洁实用，适合作为经验指导
4. 格式为JSON数组，不要其他内容

示例格式:
[
  {{"type": "knowledge_facts", "title": "PostgreSQL JSONB索引", "content": "PostgreSQL JSONB 查询应该使用 GIN 索引以提高性能"}},
  {{"type": "skills", "title": "长文本摘要技巧", "content": "使用 map-reduce 方法：先分段摘要，再合并"}},
  {{"type": "tools", "title": "Docker构建命令", "content": "docker build -t app ."}},
  {{"type": "workflows", "title": "代码审查流程", "content": "read → analyze → feedback → verify"}},
  {{"type": "user_profile", "title": "用户偏好", "content": "用户喜欢早上9点开始工作"}}
]
"""

            response = call_llm(prompt, max_tokens=2000)
            return self._parse_extraction_result(response)

        except ImportError:
            return self._extract_knowledge_fallback(content, domain_hint)
        except Exception as e:
            logger.debug("LLM extraction failed, using fallback: %s", e)
            return self._extract_knowledge_fallback(content, domain_hint)

    def _parse_extraction_result(self, response: str) -> list[dict[str, str]]:
        try:
            import json
            result = json.loads(response)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            return []

    def _extract_knowledge_fallback(self, content: str, domain_hint: str) -> list[dict[str, str]]:
        """Fallback extraction without LLM."""
        items = []
        sentences = content.replace("。", " ").replace("!", " ").replace("?", " ").split()

        domain_keywords = {
            "daily_life": ["日程", "提醒", "偏好", "习惯", "学习", "方法"],
            "agent_dev": ["agent", "loop", "tool", "skill", "prompt", "memory", "context"],
            "database": ["索引", "查询", "性能", "优化", "SQL", "表", "事务", "MongoDB"],
            "llm_usage": ["token", "prompt", "模型", "参数", "embedding", "API", "cache"],
            "network_info": ["搜索", "网页", "URL", "HTTP", "爬虫", "信息"],
            "dev_ops": ["docker", "部署", "容器", "镜像", "kubernetes", "监控", "CI"],
            "code_engineering": ["重构", "测试", "架构", "设计模式", "SOLID", "lint"],
            "project_mgmt": ["任务", "进度", "待办", "优先级", "风险", "规划"],
            "math_reasoning": ["复杂度", "算法", "概率", "线性代数", "图论", "递归"],
            "troubleshooting": ["调试", "错误", "内存泄漏", "并发", "死锁", "网络"],
            "security": ["加密", "认证", "JWT", "SQL注入", "XSS", "CSRF"],
            "data_science": ["Pandas", "机器学习", "特征工程", "可视化", "模型"],
            "system_admin": ["Linux", "Shell", "Nginx", "进程", "权限", "ssh"],
        }

        keywords = domain_keywords.get(domain_hint, [])

        for i, sentence in enumerate(sentences[:15]):
            if any(kw in sentence for kw in keywords) or i < 8:
                items.append({
                    "type": "knowledge_facts",
                    "title": sentence[:50] if len(sentence) > 50 else sentence,
                    "content": sentence[:200],
                })

        return items[:10]

    def get_stats(self) -> dict[str, Any]:
        """Return pipeline statistics."""
        warehouse_stats = self._warehouse.get_stats()
        tree_stats = self._experience_tree.get_all_stats()

        return {
            "warehouse": warehouse_stats,
            "experience_tree": tree_stats,
        }
