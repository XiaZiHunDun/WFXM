"""Tool taxonomy — organizes tools by domain for intelligent discovery.

Integrates with the Experience Tree taxonomy (taxonomy.py) to provide
consistent domain-based tool categorization.
"""

from __future__ import annotations

from typing import Any

# Tool taxonomy aligned with experience tree domains
# Each domain maps to tools that are commonly used in that context

TOOL_TAXONOMY: dict[str, dict[str, Any]] = {
    "agent_dev": {
        "name": "Agent 开发",
        "description": "LLM 编排、prompt 工程、工具集成",
        "tools": [
            "delegate_task",
            "skill_view",
            "skills_list",
            "run_workflow",
            "execute_code",
            "call_llm",
        ],
        "keywords": ["agent", "llm", "prompt", "tool", "skill", "编排", "推理"],
    },
    "database": {
        "name": "数据库使用",
        "description": "SQL/NoSQL 操作、迁移、性能调优",
        "tools": [
            "execute_code",
            "terminal",
            "read_file",
            "patch",
        ],
        "keywords": ["sql", "postgres", "mysql", "redis", "mongodb", "数据库", "索引"],
    },
    "llm_usage": {
        "name": "大模型使用",
        "description": "模型选择、参数调优、prompt 优化",
        "tools": [
            "call_llm",
            "embed_text",
            "web_search",
            "delegate_task",
        ],
        "keywords": ["model", "llm", "gpt", "claude", "deepseek", "模型", "prompt"],
    },
    "code_engineering": {
        "name": "代码工程",
        "description": "架构设计、重构、测试、代码审查",
        "tools": [
            "read_file",
            "write_file",
            "patch",
            "search_files",
            "execute_code",
            "terminal",
            "list_directory",
        ],
        "keywords": ["code", "refactor", "test", "lint", "review", "代码", "架构"],
    },
    "dev_ops": {
        "name": "开发运维",
        "description": "CI/CD、容器化、监控、部署",
        "tools": [
            "terminal",
            "run_workflow",
            "delegate_task",
            "execute_code",
            "patch",
        ],
        "keywords": ["docker", "kubernetes", "ci", "cd", "deploy", "容器", "部署"],
    },
    "network_info": {
        "name": "网络信息查找",
        "description": "搜索策略、信息抽取、事实核查",
        "tools": [
            "web_search",
            "web_fetch",
            "read_file",
            "execute_code",
        ],
        "keywords": ["search", "web", "fetch", "url", "搜索", "网页", "信息"],
    },
    "daily_life": {
        "name": "日常生活",
        "description": "用户偏好、习惯、提醒、日程",
        "tools": [
            "reminder",
            "memo",
            "habits",
            "delegate_task",
        ],
        "keywords": ["日程", "提醒", "偏好", "习惯", "天气", "生活"],
    },
    "project_mgmt": {
        "name": "项目管理",
        "description": "需求拆解、进度追踪、优先级排序",
        "tools": [
            "project_todos",
            "session_todos",
            "delegate_task",
            "run_workflow",
        ],
        "keywords": ["task", "progress", "backlog", "priority", "任务", "进度", "待办"],
    },
    "security": {
        "name": "安全防护",
        "description": "安全漏洞、加密、认证、授权",
        "tools": [
            "execute_code",
            "terminal",
            "patch",
            "search_files",
        ],
        "keywords": ["security", "encrypt", "jwt", "oauth", "安全", "加密", "认证"],
    },
    "data_science": {
        "name": "数据科学",
        "description": "数据分析、机器学习、数据可视化",
        "tools": [
            "execute_code",
            "read_file",
            "web_search",
        ],
        "keywords": ["data", "pandas", "numpy", "ml", "数据", "分析", "机器学习"],
    },
    "math_reasoning": {
        "name": "数学推导",
        "description": "数学公式、逻辑推导、算法分析",
        "tools": [
            "execute_code",
            "delegate_task",
        ],
        "keywords": ["数学", "公式", "推导", "算法", "复杂度", "概率"],
    },
    "troubleshooting": {
        "name": "故障定位",
        "description": "问题诊断、错误分析、调试技巧",
        "tools": [
            "terminal",
            "read_file",
            "search_files",
            "execute_code",
        ],
        "keywords": ["debug", "错误", "异常", "traceback", "调试", "排查", "bug"],
    },
    "system_admin": {
        "name": "系统管理",
        "description": "操作系统、网络、服务器管理",
        "tools": [
            "terminal",
            "execute_code",
            "read_file",
            "patch",
        ],
        "keywords": ["linux", "bash", "shell", "network", "server", "系统", "进程"],
    },
}

# Reverse mapping: tool_name -> list of domains
_TOOL_TO_DOMAINS: dict[str, list[str]] = {}


def _build_reverse_mapping() -> None:
    """Build reverse mapping from tool name to domains."""
    global _TOOL_TO_DOMAINS
    _TOOL_TO_DOMAINS = {}
    for domain_id, domain_info in TOOL_TAXONOMY.items():
        for tool_name in domain_info.get("tools", []):
            if tool_name not in _TOOL_TO_DOMAINS:
                _TOOL_TO_DOMAINS[tool_name] = []
            _TOOL_TO_DOMAINS[tool_name].append(domain_id)


_build_reverse_mapping()


def get_tools_by_domain(domain_id: str) -> list[str]:
    """Get all tools for a specific domain."""
    domain_info = TOOL_TAXONOMY.get(domain_id, {})
    return domain_info.get("tools", [])


def get_domains_for_tool(tool_name: str) -> list[str]:
    """Get all domains a tool belongs to."""
    return _TOOL_TO_DOMAINS.get(tool_name, [])


def get_all_tools() -> list[str]:
    """Get all unique tool names from taxonomy."""
    return list(_TOOL_TO_DOMAINS.keys())


def get_domain_for_query(query: str) -> str:
    """Determine the most likely domain for a query."""
    from butler.memory.experience.domain_router import DomainRouter
    router = DomainRouter()
    domain_id, _ = router.route(query)
    return domain_id


def get_recommended_tools(query: str, top_k: int = 5) -> list[str]:
    """Get recommended tools for a query based on domain taxonomy."""
    domain_id = get_domain_for_query(query)
    domain_tools = get_tools_by_domain(domain_id)
    
    # Also check query for direct tool mentions
    q_lower = query.lower()
    all_tools = get_all_tools()
    direct_mentions = [t for t in all_tools if t.replace("_", " ") in q_lower or t in q_lower]
    
    # Combine and deduplicate
    seen = set()
    result = []
    for tool in direct_mentions + domain_tools:
        if tool not in seen:
            seen.add(tool)
            result.append(tool)
    
    return result[:top_k]


def get_tool_description(tool_name: str) -> str | None:
    """Get the description for a tool from registry."""
    from butler.tools.registry import _REGISTRY, _ensure_builtins
    _ensure_builtins()
    entry = _REGISTRY.get(tool_name)
    if entry:
        return entry.description
    return None


def get_tool_info(tool_name: str) -> dict[str, Any]:
    """Get comprehensive info about a tool."""
    domains = get_domains_for_tool(tool_name)
    description = get_tool_description(tool_name)
    
    return {
        "name": tool_name,
        "domains": domains,
        "primary_domain": domains[0] if domains else None,
        "description": description,
        "is_registered": description is not None,
    }