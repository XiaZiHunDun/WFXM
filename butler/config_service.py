"""Runtime configuration service — read / write Butler settings from conversation.

Provides a white-listed set of BUTLER_* keys that can be queried and changed
at runtime.  Changes to level-A keys take effect immediately (os.environ);
level-B keys additionally reset the current AgentLoop; level-C keys return
a "restart required" hint.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from butler.defaults.env_defaults import ONBOARDING_WELCOME_DEFAULT

logger = logging.getLogger(__name__)


@dataclass
class ConfigMeta:
    key: str
    category: str          # 网络 / 安全 / 记忆 / 开发 / 网关 / 日常 / 系统
    description: str
    default: str
    level: str             # A=immediate, B=reset_loop, C=restart
    value_type: str = "bool"  # bool / int / str


@dataclass
class ConfigValue:
    key: str
    effective: str
    source: str            # env / yaml / default
    meta: ConfigMeta | None = None


@dataclass
class ConfigResult:
    ok: bool
    message: str
    needs_reset: bool = False
    needs_restart: bool = False


# White-listed mutable keys (security: no API keys, no paths like BUTLER_HOME)
_MUTABLE_KEYS: dict[str, ConfigMeta] = {}


def _register(key: str, cat: str, desc: str, default: str, level: str = "A", vtype: str = "bool") -> None:
    _MUTABLE_KEYS[key] = ConfigMeta(
        key=key, category=cat, description=desc,
        default=default, level=level, value_type=vtype,
    )


# --- 网络 ---
_register("BUTLER_ENABLE_WEB_FETCH", "网络", "公网 URL 抓取", "0")
_register("BUTLER_ENABLE_WEB_SEARCH", "网络", "网络搜索", "0")
_register("BUTLER_WEB_SEARCH_TIMEOUT", "网络", "web_search 单次尝试超时（秒）", "15", vtype="int")
_register("BUTLER_WEB_SEARCH_BUDGET", "网络", "web_search 总时间预算（秒）", "60", vtype="int")
_register("BUTLER_FIRECRAWL_AGENT_MAX_PER_TURN", "网络", "firecrawl_agent 每轮上限", "0", vtype="int")
_register("BUTLER_FIRECRAWL_FEEDBACK_MAX_PER_TURN", "网络", "firecrawl_feedback 每轮上限", "0", vtype="int")
_register("BUTLER_ENABLE_DOWNLOAD", "网络", "HTTPS 文件下载", "0")
_register("BUTLER_IMAGE_GENERATION", "网络", "图像生成工具", "1")
_register("BUTLER_TTS", "网络", "语音合成工具", "1")
_register("BUTLER_WEB_FETCH_TIMEOUT", "网络", "web_fetch 超时（秒）", "20", vtype="int")
_register("BUTLER_WEB_FETCH_MAX_BYTES", "网络", "web_fetch 响应字节上限", "65536", vtype="int")
# --- 安全 ---
# Sprint 9 SEC-9.1: 5 个安全类 key（DOOM_LOOP_THRESHOLD / DOOM_LOOP_MODE /
# TERMINAL_DANGER_CHECK / IO_GUARDRAIL / READ_BEFORE_EDIT）从 _MUTABLE_KEYS
# 移出。运行时不可改 — 启动期 env 或 yaml 才能决定。
# --- 记忆 ---
_register("BUTLER_SEMANTIC_MEMORY", "记忆", "本地向量语义搜索", "1")
_register("BUTLER_SYNC_CONVERSATION_MEMORY", "记忆", "每轮聊天写入 experience", "0")
_register("BUTLER_QUEUE_PREFETCH", "记忆", "下轮预取缓存", "1")
_register("BUTLER_CORRECTIVE_RECALL", "记忆", "工具失败纠错检索", "1")
# --- 开发 ---
_register("BUTLER_ENABLE_GIT", "开发", "Git 只读工具", "1")
_register("BUTLER_ENABLE_GIT_WRITE", "开发", "Git 写入工具", "0")
_register("BUTLER_POST_EDIT_FORMAT", "开发", "编辑后自动格式化（ruff/prettier）", "0")
_register("BUTLER_DATA_QUERY", "开发", "DuckDB 数据查询", "1")
# Sprint 9 SEC-9.1: 3 个开发类 key（ENABLE_TERMINAL / ENABLE_GIT_PUSH /
# EXECUTE_CODE）从 _MUTABLE_KEYS 移出 — 运行时不可改。
# --- 网关 ---
_register("BUTLER_GATEWAY_TYPING_ENABLED", "网关", "输入状态提示", "1")
_register("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "网关", "长任务进度确认", "1")
_register("BUTLER_GATEWAY_TASK_MILESTONE", "网关", "结构化进度里程碑", "0")
_register("BUTLER_GATEWAY_COMPLETION_NOTIFY", "网关", "长任务完成推送", "1")
_register("BUTLER_DELEGATE_ASYNC", "网关", "微信委派后台执行", "1")
_register("BUTLER_WECHAT_CONTENT_DEDUP_TTL", "网关", "微信内容去重 TTL（秒）", "20", vtype="int")
_register("BUTLER_WECHAT_MESSAGE_ID_DEDUP_TTL", "网关", "微信消息 ID 去重 TTL（秒）", "300", vtype="int")
# --- 日常 ---
_register("BUTLER_MEMO_ENABLED", "日常", "备忘录模块", "1")
_register("BUTLER_CONTACTS_ENABLED", "日常", "通讯录模块", "1")
_register("BUTLER_EXPENSE_ENABLED", "日常", "记账模块", "1")
_register("BUTLER_HABITS_ENABLED", "日常", "习惯打卡模块", "1")
# --- MCP/Skill ---
_register("BUTLER_MCP_ENABLED", "扩展", "MCP 薄客户端", "0")
_register("BUTLER_MCP_SELF_SERVICE", "扩展", "MCP 自助安装工具", "1")
_register("BUTLER_SKILL_REGISTRY", "扩展", "Skill 目录搜索", "1")
# --- 系统 ---
_register("BUTLER_LOG_LEVEL", "系统", "日志级别", "INFO", vtype="str")
_register("BUTLER_DISABLE_AUTO_COMPACT", "系统", "关闭自动压缩", "0")
_register("BUTLER_AUTO_CONTINUE", "系统", "中断后自动恢复", "1")
_register("BUTLER_ONBOARDING_WELCOME", "系统", "新会话欢迎语", ONBOARDING_WELCOME_DEFAULT)
_register("BUTLER_POST_SESSION_LAYERED", "系统", "会话后自动偏好学习", "0")

# Category display order
_CATEGORIES = ["网络", "安全", "记忆", "开发", "网关", "日常", "扩展", "系统"]


def config_get(key: str) -> ConfigValue:
    """Read the effective value and source of a BUTLER_* key."""
    key = key.upper().strip()
    meta = _MUTABLE_KEYS.get(key)
    env_val = os.getenv(key, "")
    if env_val:
        return ConfigValue(key=key, effective=env_val, source="env", meta=meta)
    if meta:
        return ConfigValue(key=key, effective=meta.default, source="default", meta=meta)
    return ConfigValue(key=key, effective="(未知)", source="unknown")


def config_set(key: str, value: str) -> ConfigResult:
    """Set a BUTLER_* key at runtime."""
    key = key.upper().strip()
    meta = _MUTABLE_KEYS.get(key)
    if meta is None:
        return ConfigResult(ok=False, message=f"不允许修改 {key}（不在白名单中或为敏感配置）")

    if meta.value_type == "bool" and value.lower() not in ("0", "1", "true", "false", "yes", "no", "on", "off"):
        return ConfigResult(ok=False, message=f"{key} 是布尔值，请使用 0/1/true/false/yes/no")
    if meta.value_type == "int":
        try:
            int(value)
        except ValueError:
            return ConfigResult(ok=False, message=f"{key} 需要整数值")

    os.environ[key] = value

    if meta.level == "C":
        return ConfigResult(ok=True, message=f"{key} 已设为 {value}（需重启 Gateway 才能完全生效）", needs_restart=True)
    if meta.level == "B":
        return ConfigResult(ok=True, message=f"{key} 已设为 {value}（当前会话将重建）", needs_reset=True)
    return ConfigResult(ok=True, message=f"{key} 已设为 {value}（立即生效）")


def reset_runtime_config_env() -> None:
    """Remove runtime-mutable BUTLER_* keys from os.environ (pytest isolation)."""
    for key in _MUTABLE_KEYS:
        os.environ.pop(key, None)


def config_list(category: str = "") -> list[ConfigValue]:
    """List config keys, optionally filtered by category."""
    cat = category.strip()
    results = []
    for key, meta in sorted(_MUTABLE_KEYS.items()):
        if cat and meta.category != cat:
            continue
        results.append(config_get(key))
    return results


def config_categories() -> list[str]:
    return list(_CATEGORIES)


def format_config_list(category: str = "") -> str:
    """Format config listing for WeChat display."""
    if not category:
        lines = ["Butler 配置分组\n"]
        for cat in _CATEGORIES:
            count = sum(1 for m in _MUTABLE_KEYS.values() if m.category == cat)
            lines.append(f"  {cat}（{count} 项）→ /config list {cat}")
        lines.append("\n查看: /config get <变量名>")
        lines.append("修改: /config set <变量名> <值>")
        return "\n".join(lines)

    items = config_list(category)
    if not items:
        return f"未找到分组: {category}\n可用分组: {', '.join(_CATEGORIES)}"
    lines = [f"配置 — {category}\n"]
    for cv in items:
        meta = cv.meta
        if meta:
            flag = "●" if cv.effective not in ("0", "false", "") else "○"
            lines.append(f"  {flag} {cv.key}={cv.effective}  ({meta.description})")
        else:
            lines.append(f"  {cv.key}={cv.effective}")
    return "\n".join(lines)


def format_config_get(key: str) -> str:
    """Format single config value for WeChat display."""
    cv = config_get(key)
    if cv.source == "unknown":
        return f"未知配置项: {key}\n\n使用 /config list 查看可用配置"
    lines = [f"{cv.key}"]
    lines.append(f"  当前值: {cv.effective}")
    lines.append(f"  来源: {cv.source}")
    if cv.meta:
        lines.append(f"  默认值: {cv.meta.default}")
        lines.append(f"  说明: {cv.meta.description}")
        lines.append(f"  分组: {cv.meta.category}")
        level_desc = {"A": "立即生效", "B": "需重建会话", "C": "需重启"}
        lines.append(f"  生效: {level_desc.get(cv.meta.level, cv.meta.level)}")
    return "\n".join(lines)
