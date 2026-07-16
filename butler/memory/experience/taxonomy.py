"""Taxonomy definitions: 8 domains × 8 categories.

Domains (Layer 1) — coarse-grained knowledge areas that map to user scenarios.
Categories (Layer 2) — fine-grained classification within each domain.
"""

from __future__ import annotations

DOMAINS: dict[str, dict] = {
    "daily_life": {
        "name": "日常生活",
        "description": "用户偏好、习惯、提醒、日程",
        "keywords": ["日程", "提醒", "偏好", "习惯", "天气", "时间", "日历", "备忘",
                      "生活", "饮食", "运动", "健康", "购物", "出行"],
    },
    "agent_dev": {
        "name": "Agent 开发",
        "description": "LLM 编排、prompt 工程、工具集成",
        "keywords": ["agent", "loop", "prompt", "tool", "skill", "llm", "编排",
                      "推理", "对话", "multi-turn", "react", "chain", "delegate",
                      "butler", "wfxm", "记忆", "上下文", "压缩", "摘要",
                      "fastapi", "flask", "django", "api", "oauth", "auth",
                      "authentication", "authorization", "jwt"],
    },
    "database": {
        "name": "数据库使用",
        "description": "SQL/NoSQL 操作、迁移、性能调优",
        "keywords": ["sql", "postgres", "redis", "index", "migration", "query",
                      "数据库", "表", "索引", "查询", "缓存", "mongo", "sqlite",
                      "chromadb", "向量", "embedding", "jsonb", "gin",
                      "postgresql", "mysql", "optimization", "performance",
                      "partition", "connection", "pool", "transaction"],
    },
    "llm_usage": {
        "name": "大模型使用",
        "description": "模型选择、参数调优、prompt 优化、模型微调",
        "keywords": ["model", "deepseek", "minimax", "token", "embedding",
                      "temperature", "top_p", "max_tokens", "system_prompt",
                      "fine-tune", "rerank", "语义", "模型", "api_key",
                      "fallback", "retry", "streaming", "prompt engineering",
                      "few-shot", "chain-of-thought", "cot", "rag",
                      "transformer", "fine tuning", "peft", "lora",
                      "prompt engineering techniques"],
    },
    "network_info": {
        "name": "网络信息查找",
        "description": "搜索策略、信息抽取、事实核查",
        "keywords": ["search", "web", "fetch", "url", "爬取", "搜索", "网页",
                      "链接", "http", "request", "crawl", "scrape", "新闻",
                      "资讯", "文档", "reference", "webfetch", "websearch"],
    },
    "dev_ops": {
        "name": "开发运维",
        "description": "CI/CD、容器化、监控、部署",
        "keywords": ["docker", "ci", "cd", "deploy", "kubernetes", "k8s",
                      "container", "镜像", "部署", "运维", "监控", "prometheus",
                      "grafana", "log", "nginx", "systemd", "cron", "shell",
                      "containerization", "best practices", "production",
                      "registry", "dockerfile", "compose", "network", "volume"],
    },
    "code_engineering": {
        "name": "代码工程",
        "description": "架构设计、重构、测试、代码审查",
        "keywords": ["refactor", "test", "lint", "review", "architecture",
                      "重构", "测试", "架构", "代码", "mypy", "pytest",
                      "type", "import", "module", "layer", "dependency",
                      "design", "pattern", "solid", "clean"],
    },
    "project_mgmt": {
        "name": "项目管理",
        "description": "需求拆解、进度追踪、优先级排序",
        "keywords": ["task", "progress", "backlog", "priority", "deadline",
                      "任务", "进度", "待办", "优先级", "里程碑", "sprint",
                      "agile", "kanban", "shift", "blackboard", "todo",
                      "规划", "排期", "交接"],
    },
    "math_reasoning": {
        "name": "数学推导",
        "description": "数学公式、逻辑推导、算法分析",
        "keywords": ["数学", "公式", "推导", "算法", "复杂度", "证明",
                      "calculus", "linear", "algebra", "probability", "statistics",
                      "算法分析", "时间复杂度", "空间复杂度", "递推", "递归"],
    },
    "troubleshooting": {
        "name": "故障定位",
        "description": "问题诊断、错误分析、调试技巧",
        "keywords": ["debug", "错误", "异常", "traceback", "log", "排查",
                      "bug", "error", "crash", "segmentation", "memory", "leak",
                      "性能问题", "死锁", "并发", "超时", "连接池"],
    },
    "security": {
        "name": "安全防护",
        "description": "安全漏洞、加密、认证、授权",
        "keywords": ["security", "安全", "加密", "hash", "jwt", "oauth",
                      "csrf", "xss", "sql注入", "认证", "授权", "密钥",
                      "ssl", "tls", "certificate", "漏洞", "渗透"],
    },
    "data_science": {
        "name": "数据科学",
        "description": "数据分析、机器学习、数据可视化",
        "keywords": ["data", "机器学习", "pandas", "numpy", "scikit", "tensorflow",
                      "数据分析", "可视化", "matplotlib", "seaborn", "特征工程",
                      "模型训练", "评估", "回归", "分类", "聚类", "nlp"],
    },
    "system_admin": {
        "name": "系统管理",
        "description": "操作系统、网络、服务器管理",
        "keywords": ["linux", "bash", "shell", "network", "server", "nginx",
                      "systemd", "service", "进程", "内存", "磁盘", "cpu",
                      "权限", "用户", "组", "防火墙", "端口", "ssh"],
    },
}

CATEGORIES: dict[str, dict] = {
    "skills": {
        "name": "技能",
        "description": "已注册的 Skill 定义、使用经验、触发条件",
        "backend": "sqlite+chromadb",
    },
    "tools": {
        "name": "工具",
        "description": "已注册的 Tool 定义、调用经验、参数模板",
        "backend": "sqlite+chromadb",
    },
    "mcp": {
        "name": "MCP 服务",
        "description": "MCP 服务器列表、能力声明、调用记录",
        "backend": "sqlite",
    },
    "workflows": {
        "name": "工作流",
        "description": "多步骤编排模板、执行经验、检查点",
        "backend": "sqlite+yaml",
    },
    "user_profile": {
        "name": "用户画像",
        "description": "偏好、技能水平、工作习惯",
        "backend": "sqlite",
    },
    "local_products": {
        "name": "本地产品",
        "description": "已接入的产品实例、配置、使用经验",
        "backend": "sqlite",
    },
    "recent_conversations": {
        "name": "近期对话",
        "description": "章节摘要、关键决策、技术栈",
        "backend": "chromadb+sqlite",
    },
    "knowledge_facts": {
        "name": "知识事实",
        "description": "领域知识点、三元组、最佳实践",
        "backend": "knowledge_graph+sqlite",
    },
}


def get_all_domain_keywords() -> dict[str, list[str]]:
    """Return domain_id → keywords mapping for routing."""
    return {did: d["keywords"] for did, d in DOMAINS.items()}


def get_domain_name(domain_id: str) -> str:
    return DOMAINS.get(domain_id, {}).get("name", domain_id)


def get_category_name(category_id: str) -> str:
    return CATEGORIES.get(category_id, {}).get("name", category_id)


def get_category_backend(category_id: str) -> str:
    return CATEGORIES.get(category_id, {}).get("backend", "sqlite")
