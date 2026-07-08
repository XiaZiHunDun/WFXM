"""Owner ingest shortcuts: manifest phrases → MarkItDown MCP + .butler/ingest (PROD-P5-02)."""

from __future__ import annotations

import re
from pathlib import Path

_INGEST_SIGNAL_RE = re.compile(
    r"(放进记忆|\bingest\b|\.butler/ingest|写入\s*ingest|参考书.*记忆)",
    re.I,
)
_MARKITDOWN_INGEST_RE = re.compile(
    r"(markitdown|mcp_markitdown).*(记忆|ingest|参考书)|"
    r"(记忆|ingest|参考书).*(markitdown|mcp_markitdown)",
    re.I,
)
_CONVERT_TO_MD_RE = re.compile(r"转成\s*markdown|转换为\s*markdown|转\s*markdown", re.I)
_PROJECT_PATH_RE = re.compile(
    r"(?:docs|novel-factory/references|references|novel-factory)/[\w./_-]+",
    re.I,
)
_REMEMBER_ONLY_RE = re.compile(
    r"^(请记住|记住：|butler_remember|/批准记忆)",
    re.I,
)


def looks_owner_ingest_intent(text: str) -> bool:
    """True when Owner likely means EXT-5 document ingest, not butler_remember."""
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    if _REMEMBER_ONLY_RE.search(raw):
        return False
    if _INGEST_SIGNAL_RE.search(raw):
        return True
    if _MARKITDOWN_INGEST_RE.search(raw):
        return True
    if _CONVERT_TO_MD_RE.search(raw) and "记忆" in raw and "请记住" not in raw:
        return True
    return False


def _extract_project_path(text: str) -> str:
    match = _PROJECT_PATH_RE.search(str(text or ""))
    if not match:
        return ""
    path = match.group(0).strip().lstrip("/")
    if ".." in path.split("/"):
        return ""
    return path


def _ingest_output_rel(path: str) -> str:
    if path:
        stem = Path(path).stem or "document"
        parent = str(Path(path).parent).replace("\\", "/").strip(".")
        if parent and parent != ".":
            return f".butler/ingest/{parent}/{stem}.md"
        return f".butler/ingest/{stem}.md"
    return ".butler/ingest/"


def build_ingest_delegate_prompt(
    *,
    source_path: str = "",
    project_name: str = "",
    workspace: str = "",
    user_text: str = "",
) -> str:
    """Explicit MarkItDown MCP + ingest path (avoid butler_remember quiz)."""
    proj = f"当前项目 {project_name}。" if project_name else ""
    ws = str(workspace or "").strip()
    ws_hint = f"workspace={ws}。" if ws else ""
    src = str(source_path or "").strip()
    out_rel = _ingest_output_rel(src)

    if src:
        src_line = f"源文件（项目内相对路径）：{src}。"
    else:
        src_line = "源：用户刚发的 PDF/附件或消息里指定的项目内文件。"

    return (
        f"【EXT-5 ingest 路由】{proj}{ws_hint}"
        f"{src_line}"
        "请优先用 MarkItDown MCP（mcp_markitdown_convert_to_markdown）转换，"
        f"将结果写入项目 workspace 下 `{out_rel}`（document ingest）。"
        "不要写入 butler_remember / MEMORY 长期约定；不要反问「是否存入长期记忆」。"
        "若 MCP 不可用，可委派 content 代理写盘到同一路径。"
        "完成后回复必须包含 ingest 路径与转换摘要。"
        f"（Owner 原话：{str(user_text or '').strip()[:120]}）"
    )


def try_expand_owner_ingest_phrase(
    text: str,
    *,
    project_name: str = "",
    workspace: str = "",
) -> str | None:
    """Expand ingest manifest phrases before the agent loop."""
    raw = str(text or "").strip()
    if not looks_owner_ingest_intent(raw):
        return None
    path = _extract_project_path(raw)
    return build_ingest_delegate_prompt(
        source_path=path,
        project_name=project_name,
        workspace=workspace,
        user_text=raw,
    )


__all__ = [
    "build_ingest_delegate_prompt",
    "looks_owner_ingest_intent",
    "try_expand_owner_ingest_phrase",
]
