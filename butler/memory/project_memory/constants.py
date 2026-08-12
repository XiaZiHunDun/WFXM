from __future__ import annotations

import re

_SECTION_ORDER = (
    "Architecture",
    "Decisions",
    "Patterns",
    "API",
    "Notes",
    "Pending",
)

_DECISION_KEYWORDS = frozenset(
    {
        "决定",
        "决策",
        "选择",
        "改为",
        "替换",
        "弃用",
        "废弃",
        "迁移",
        "重构",
        "升级",
        "降级",
        "切换",
        "采用",
        "放弃",
        "转向",
        "decided",
        "decision",
        "chose",
        "choose",
        "switch",
        "migrate",
        "migrating",
        "replace",
        "deprecate",
        "adopt",
        "abandon",
        "we should",
        "we will",
        "going to",
    }
)

_SENSITIVE_PII_RE = re.compile(
    r"("
    r"1[3-9]\d{9}"
    r"|sk-[a-z0-9]{8,}"
    r"|eyJ[a-z0-9_-]{10,}\.[a-z0-9_-]+\.[a-z0-9_-]+"
    r"|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"|\b(?:api[_-]?key|secret|password|token|credential)s?\b"
    r"|密码|密钥|口令|身份证|银行卡|手机号"
    r")",
    re.I,
)

_SENSITIVE_PENDING_KEYWORDS = frozenset(
    {
        "批准",
        "permission",
        "owner only",
        "始终允许",
        "wechat_id",
        "chat_id",
        "credential",
        "credentials",
    }
)

_PENDING_UNCERTAIN = frozenset(
    {
        "maybe",
        "perhaps",
        "不确定",
        "待确认",
        "待定",
        "考虑",
        "possibly",
        "tbd",
        "wip",
    }
)

_ROLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "dev": ("Architecture", "Patterns", "API", "Notes"),
    "developer": ("Architecture", "Patterns", "API", "Notes"),
    "dev_agent": ("Architecture", "Patterns", "API", "Notes"),
    "impl": ("Architecture", "Patterns", "API"),
    "code": ("Architecture", "Patterns", "API"),
    "content": ("Notes", "Patterns", "Decisions"),
    "content_agent": ("Notes", "Patterns", "Decisions"),
    "review": ("Architecture", "Decisions", "Patterns"),
    "reviewer": ("Architecture", "Decisions", "Patterns"),
    "review_agent": ("Architecture", "Decisions", "Patterns"),
    "lead": ("Architecture", "Decisions", "Notes"),
    "butler": ("Decisions", "Notes", "Architecture"),
    "plan": ("Architecture", "Decisions", "Notes"),
    "architect": ("Architecture", "Decisions", "Patterns", "API"),
    "default": ("Architecture", "Decisions", "Patterns", "API", "Notes"),
}

_ROLE_PREFETCH_PROJECT_MAX_CHARS: dict[str, int] = {
    "lead": 800,
    "butler": 900,
    "content": 900,
    "content_agent": 900,
    "review": 1000,
    "review_agent": 1000,
    "dev": 1200,
    "dev_agent": 1200,
}

_PENDING_LINE_RE = re.compile(
    r"^-\s*\[PENDING\]\s*\[target:(?P<target>[^\]]+)\]\s*\[(?P<ts>[^\]]+)\]\s*(?P<body>.+)$"
)

_SECTION_ALIASES: dict[str, str] = {
    "架构与设计": "Architecture",
    "架构": "Architecture",
    "设计": "Architecture",
    "关键决策": "Decisions",
    "决策": "Decisions",
    "代码模式与约定": "Patterns",
    "代码模式": "Patterns",
    "约定": "Patterns",
    "已知问题": "Notes",
    "问题": "Notes",
    "当前状态": "Notes",
    "状态": "Notes",
    "接口": "API",
}
