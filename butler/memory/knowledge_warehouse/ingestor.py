"""MaterialIngestor — receives materials from various sources and normalizes them.

Supported sources:
- text: direct text content
- url: web page URL (fetches content)
- file: local file path (reads file content)
- markdown: markdown content with metadata
- code: code snippets with language info
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse

logger = logging.getLogger(__name__)


class MaterialIngestor:
    def __init__(self, warehouse: KnowledgeWarehouse | None = None):
        self._warehouse = warehouse or KnowledgeWarehouse()

    def ingest_text(
        self,
        content: str,
        domain_hint: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        source: str = "ai_collected",
        source_file: str = "",
    ) -> tuple[str, bool]:
        """Ingest plain text content.
        
        Args:
            source: 'user_collected' or 'ai_collected' to distinguish knowledge source
            source_file: Original file path for file-based materials
        """
        normalized = self._normalize_text(content)
        if not normalized:
            raise ValueError("Empty content after normalization")

        material_id, was_added = self._warehouse.add_material(
            domain_hint=domain_hint,
            raw_content=normalized,
            source_type="text",
            title=title or self._extract_title(normalized),
            source_file=source_file,
            metadata={"source": source, **(metadata or {})},
            priority=priority,
        )

        if was_added:
            logger.info("Ingested text material: %s", material_id)
        else:
            logger.debug("Material already exists: %s", material_id)

        return material_id, was_added

    def ingest_url(
        self,
        url: str,
        domain_hint: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        source: str = "ai_collected",
    ) -> tuple[str, bool]:
        """Ingest a web page URL."""
        try:
            content = self._fetch_url_content(url)
            if not content:
                raise ValueError("Failed to fetch URL content")

            material_id, was_added = self._warehouse.add_material(
                domain_hint=domain_hint,
                raw_content=content,
                source_type="url",
                title=title or self._extract_title(content),
                source_url=url,
                metadata={"source": source, **(metadata or {})},
                priority=priority,
            )

            if was_added:
                logger.info("Ingested URL material: %s from %s", material_id, url)
            else:
                logger.debug("URL material already exists: %s", material_id)

            return material_id, was_added
        except Exception as e:
            logger.error("Failed to ingest URL %s: %s", url, e)
            raise

    def ingest_file(
        self,
        file_path: str,
        domain_hint: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        source: str = "ai_collected",
    ) -> tuple[str, bool]:
        """Ingest a local file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            content = self._read_file_content(file_path)
            if not content:
                raise ValueError("Empty file content")

            ext = os.path.splitext(file_path)[1].lower()
            title = title or os.path.basename(file_path)

            material_id, was_added = self._warehouse.add_material(
                domain_hint=domain_hint,
                raw_content=content,
                source_type="file",
                title=title,
                source_file=file_path,
                metadata={
                    "file_extension": ext,
                    "source": source,
                    **(metadata or {}),
                },
                priority=priority,
            )

            if was_added:
                logger.info("Ingested file material: %s from %s", material_id, file_path)
            else:
                logger.debug("File material already exists: %s", material_id)

            return material_id, was_added
        except Exception as e:
            logger.error("Failed to ingest file %s: %s", file_path, e)
            raise

    def ingest_markdown(
        self,
        content: str,
        domain_hint: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        source: str = "ai_collected",
        source_file: str = "",
    ) -> tuple[str, bool]:
        """Ingest markdown content with metadata extraction."""
        normalized = self._normalize_markdown(content)
        title = title or self._extract_title(normalized)

        material_id, was_added = self._warehouse.add_material(
            domain_hint=domain_hint,
            raw_content=normalized,
            source_type="markdown",
            title=title,
            source_file=source_file,
            metadata={
                "format": "markdown",
                "source": source,
                **(metadata or {}),
            },
            priority=priority,
        )

        if was_added:
            logger.info("Ingested markdown material: %s", material_id)
        else:
            logger.debug("Markdown material already exists: %s", material_id)

        return material_id, was_added

    def ingest_code(
        self,
        code: str,
        language: str,
        domain_hint: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        source: str = "ai_collected",
        source_file: str = "",
    ) -> tuple[str, bool]:
        """Ingest code snippets with language info."""
        content = f"```\n{code}\n```"

        material_id, was_added = self._warehouse.add_material(
            domain_hint=domain_hint,
            raw_content=content,
            source_type="code",
            title=title or f"{language} code snippet",
            source_file=source_file,
            metadata={
                "language": language,
                "format": "code",
                "source": source,
                **(metadata or {}),
            },
            priority=priority,
        )

        if was_added:
            logger.info("Ingested code material: %s (%s)", material_id, language)
        else:
            logger.debug("Code material already exists: %s", material_id)

        return material_id, was_added

    def enqueue_material(self, material_id: str) -> None:
        """Enqueue a material for digestion."""
        self._warehouse.enqueue_for_digestion(material_id)
        logger.info("Enqueued material for digestion: %s", material_id)

    def bulk_ingest(
        self,
        materials: list[dict[str, Any]],
    ) -> list[tuple[str, bool]]:
        """Bulk ingest multiple materials."""
        results = []
        for material in materials:
            source_type = material.get("source_type", "text")
            try:
                if source_type == "text":
                    result = self.ingest_text(
                        content=material["content"],
                        domain_hint=material.get("domain_hint", ""),
                        title=material.get("title", ""),
                        metadata=material.get("metadata"),
                        priority=material.get("priority", 0),
                    )
                elif source_type == "url":
                    result = self.ingest_url(
                        url=material["url"],
                        domain_hint=material.get("domain_hint", ""),
                        title=material.get("title", ""),
                        metadata=material.get("metadata"),
                        priority=material.get("priority", 0),
                    )
                elif source_type == "file":
                    result = self.ingest_file(
                        file_path=material["file_path"],
                        domain_hint=material.get("domain_hint", ""),
                        title=material.get("title", ""),
                        metadata=material.get("metadata"),
                        priority=material.get("priority", 0),
                    )
                elif source_type == "markdown":
                    result = self.ingest_markdown(
                        content=material["content"],
                        domain_hint=material.get("domain_hint", ""),
                        title=material.get("title", ""),
                        metadata=material.get("metadata"),
                        priority=material.get("priority", 0),
                    )
                elif source_type == "code":
                    result = self.ingest_code(
                        code=material["code"],
                        language=material["language"],
                        domain_hint=material.get("domain_hint", ""),
                        title=material.get("title", ""),
                        metadata=material.get("metadata"),
                        priority=material.get("priority", 0),
                    )
                else:
                    logger.warning("Unknown source_type: %s", source_type)
                    continue

                results.append(result)

                if result[1]:
                    self.enqueue_material(result[0])

            except Exception as e:
                logger.error("Failed to ingest material: %s", e)

        return results

    def _normalize_text(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _normalize_markdown(self, content: str) -> str:
        return self._normalize_text(content)

    def _extract_title(self, content: str) -> str:
        lines = content.split("\n")
        for line in lines[:5]:
            if line.startswith("# "):
                return line[2:].strip()
            if line.strip() and len(line.strip()) < 100:
                return line.strip()[:80]
        return "Untitled"

    def _fetch_url_content(self, url: str) -> str:
        try:
            import requests
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except ImportError:
            raise RuntimeError("requests library not installed")
        except Exception as e:
            logger.error("Failed to fetch URL: %s", e)
            return ""

    def batch_import_directory(
        self,
        directory: str,
        recursive: bool = True,
        domain_hint: str = "",
        source: str = "ai_collected",
    ) -> list[tuple[str, bool]]:
        """Batch import all files from a directory.

        Args:
            directory: Path to the directory to scan
            recursive: Whether to scan subdirectories
            domain_hint: Override domain hint (if not provided, auto-detects from content)
            source: 'user_collected' or 'ai_collected' to distinguish knowledge source

        Returns:
            List of (material_id, was_added) tuples
        """
        if not os.path.isdir(directory):
            raise ValueError(f"Not a directory: {directory}")

        EXTENSION_TYPE_MAP = {
            ".md": "markdown",
            ".markdown": "markdown",
            ".txt": "text",
            ".py": "code",
            ".json": "text",
            ".csv": "text",
            ".yml": "text",
            ".yaml": "text",
            ".html": "text",
            ".rst": "markdown",
        }

        results = []
        files_scanned = 0
        files_ingested = 0

        for root, dirs, files in os.walk(directory):
            if not recursive:
                dirs[:] = []

            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()

                if ext not in EXTENSION_TYPE_MAP:
                    logger.debug("Skipping unsupported file: %s", filename)
                    continue

                source_type = EXTENSION_TYPE_MAP[ext]
                files_scanned += 1

                content = self._read_file_content(file_path)
                auto_domain = self._detect_domain_from_content(content) if not domain_hint else domain_hint

                try:
                    if source_type == "markdown":
                        result = self.ingest_markdown(
                            content=content,
                            domain_hint=auto_domain,
                            title=os.path.splitext(filename)[0],
                            metadata={},
                            source=source,
                            source_file=file_path,
                        )
                    elif source_type == "code":
                        result = self.ingest_code(
                            code=content,
                            language="python",
                            domain_hint=auto_domain,
                            title=filename,
                            metadata={},
                            source=source,
                            source_file=file_path,
                        )
                    else:
                        result = self.ingest_text(
                            content=content,
                            domain_hint=auto_domain,
                            title=os.path.splitext(filename)[0],
                            metadata={"file_extension": ext},
                            source=source,
                            source_file=file_path,
                        )

                    results.append(result)
                    if result[1]:
                        files_ingested += 1
                        self.enqueue_material(result[0])
                        logger.info("Ingested %s file: %s -> domain: %s", source, filename, auto_domain)

                except Exception as e:
                    logger.error("Failed to ingest file %s: %s", file_path, e)

        logger.info("Batch import completed: scanned=%d, ingested=%d", files_scanned, files_ingested)
        return results

    def _detect_domain_from_content(self, content: str) -> str:
        """Auto-detect domain from content keywords.

        Returns:
            Detected domain name or empty string if unsure
        """
        content_lower = content.lower()

        domain_keywords = {
            "daily_life": [
                "日程", "提醒", "偏好", "习惯", "学习", "方法", "时间管理", "生活",
                "健康", "饮食", "运动", "旅行", "购物", "娱乐", "阅读", "休息"
            ],
            "agent_dev": [
                "agent", "loop", "tool", "skill", "prompt", "memory", "context",
                "llm", "chatbot", "workflow", "orchestration", "react", "planning"
            ],
            "database": [
                "索引", "查询", "性能", "优化", "sql", "表", "事务", "mongodb",
                "redis", "postgresql", "mysql", "schema", "join", "index", "cache"
            ],
            "llm_usage": [
                "token", "prompt", "模型", "参数", "embedding", "api", "cache",
                "fine-tune", "rag", "vector", "semantic", "generation", "completion"
            ],
            "network_info": [
                "搜索", "网页", "url", "http", "爬虫", "信息", "api", "request",
                "response", "scraping", "fetch", "crawl", "browser", "selenium"
            ],
            "dev_ops": [
                "docker", "部署", "容器", "镜像", "kubernetes", "监控", "ci",
                "cd", "jenkins", "gitlab", "github", "deployment", "monitoring"
            ],
            "code_engineering": [
                "重构", "测试", "架构", "设计模式", "solid", "lint", "debug",
                "refactor", "unittest", "pytest", "architecture", "clean code"
            ],
            "project_mgmt": [
                "任务", "进度", "待办", "优先级", "风险", "规划", "scrum",
                "kanban", "sprint", "agile", "milestone", "backlog", "estimate"
            ],
            "math_reasoning": [
                "复杂度", "算法", "概率", "线性代数", "图论", "递归", "dp",
                "sort", "search", "graph", "matrix", "calculus", "optimization"
            ],
            "troubleshooting": [
                "调试", "错误", "内存泄漏", "并发", "死锁", "网络", "crash",
                "bug", "fix", "error", "debugging", "performance", "memory"
            ],
            "security": [
                "加密", "认证", "jwt", "sql注入", "xss", "csrf", "oauth",
                "https", "ssl", "password", "token", "auth", "vulnerability"
            ],
            "data_science": [
                "pandas", "机器学习", "特征工程", "可视化", "模型", "numpy",
                "scikit", "tensorflow", "pytorch", "data analysis", "feature"
            ],
            "system_admin": [
                "linux", "shell", "nginx", "进程", "权限", "ssh", "server",
                "ubuntu", "centos", "network", "firewall", "user", "group"
            ],
        }

        scores = {}
        for domain, keywords in domain_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            scores[domain] = score

        max_score = max(scores.values())
        if max_score >= 2:
            best_domain = max(scores, key=scores.get)
            logger.debug("Auto-detected domain: %s (score: %d)", best_domain, max_score)
            return best_domain

        logger.debug("No domain detected, using empty hint")
        return ""

    def _read_file_content(self, file_path: str) -> str:
        size = os.path.getsize(file_path)
        if size > 5 * 1024 * 1024:
            logger.warning("File size %d bytes exceeds 5MB limit", size)

        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".pdf", ".docx", ".doc"):
            logger.warning("Binary file format %s may not extract text properly", ext)

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
