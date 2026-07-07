"""Registry tool helpers (P0-A)."""

from __future__ import annotations

import json
from typing import Any

from butler.core.best_effort import safe_best_effort


def default_registry_tenant_id() -> str:
    def _run() -> str:
        from butler.config import load_settings

        return str(load_settings().default_tenant or "default")

    result = safe_best_effort(
        _run,
        label="registry_tools.tenant_id",
        default="default",
    )
    return str(result or "default")


def install_skill_confirmed_json(svc: Any, identifier: str) -> str:
    try:
        result = svc.install(identifier, confirmed=True)
        return json.dumps({
            "ok": True,
            "message": f"Skill '{identifier}' 安装完成",
            "details": str(result) if result else "",
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "error": f"安装失败: {exc}",
            "hint": "可尝试 /技能 搜索 " + identifier + " 确认标识符",
        }, ensure_ascii=False)
