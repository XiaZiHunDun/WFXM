"""Dangerous shell command detection for ``run_shell`` safety checks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandCheck:
    is_dangerous: bool
    category: str = ""
    description: str = ""
    command: str = ""


DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    (r"rm\s+(-[rfRF]+\s+)?/", "destructive", "删除根目录或系统目录"),
    (r"rm\s+-[rfRF]*\s+\*", "destructive", "递归删除通配符"),
    (r"rm\s+-[rfRF]{2,}", "destructive", "强制递归删除"),
    (r"mkfs\b", "destructive", "格式化文件系统"),
    (r"dd\s+.*of=/dev/", "destructive", "写入设备文件"),
    (r":\(\){ :\|:& };:", "destructive", "Fork bomb"),
    (r"chmod\s+(-R\s+)?777", "permission", "开放所有权限"),
    (r"chmod\s+(-R\s+)?000", "permission", "移除所有权限"),
    (r"chown\s+-R\s+root", "permission", "递归改变所有者为root"),
    (r"sudo\s+", "privilege", "使用 sudo 提权"),
    (r"su\s+-?\s*$", "privilege", "切换到 root"),
    (r"curl\s+[^\n]*\|\s*(ba)?sh", "injection", "下载并执行脚本"),
    (r"wget\s+[^\n]*\|\s*(ba)?sh", "injection", "下载并执行脚本"),
    (r"eval\s+.*\$", "injection", "动态执行变量内容"),
    (r">\s*/etc/", "system", "覆写系统配置"),
    (r">\s*/dev/", "system", "写入设备文件"),
    (r"cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|id_rsa)", "secrets", "读取敏感凭证文件"),
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfiltration", "可能泄露密钥"),
    (r"git\s+push\s+.*--force", "git", "强制推送"),
    (r"git\s+reset\s+--hard", "git", "硬重置（不可恢复）"),
    (
        r"pip\s+install\s+(?!-e\s)(?!--editable).*(?:--user|--break-system-packages)",
        "package",
        "全局安装包",
    ),
    (r"npm\s+install\s+-g", "package", "全局安装npm包"),
]

_COMPILED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(p, re.IGNORECASE), cat, desc) for p, cat, desc in DANGEROUS_PATTERNS
]


def check_command(command: str) -> CommandCheck:
    text = command or ""
    for pattern, category, description in _COMPILED:
        if pattern.search(text):
            return CommandCheck(
                is_dangerous=True,
                category=category,
                description=description,
                command=text,
            )
    return CommandCheck(is_dangerous=False, command=text)


def check_and_log(command: str) -> CommandCheck:
    result = check_command(command)
    if result.is_dangerous:
        logger.warning(
            "Dangerous command pattern (%s): %s — %s",
            result.category,
            result.description,
            result.command[:500],
        )
    return result
