#!/usr/bin/env python3
"""Parse reference/用户语料/*.md → reference_utterance_catalog.yaml (CI-sized)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REF_DIR = ROOT / "reference" / "用户语料"
OUT_PATH = (
    ROOT
    / "tests"
    / "corpus"
    / "suites"
    / "wechat_real"
    / "lw_real"
    / "reference_utterance_catalog.yaml"
)
EXISTING_PATH = ROOT / "tests" / "corpus" / "suites" / "wechat_real" / "lw_real" / "utterance_catalog.yaml"

_SECTION_CAT = {
    "A.": "project_session",
    "B.": "read_only",
    "C.": "delegate_file",
    "D.": "detail_report",
    "E.": "memory_ops",
    "F.": "workflow_runtime",
    "G.": "safety_boundary",
    "H.": "intro_capability",
}


def _is_doc_noise(user: str) -> bool:
    """Skip markdown doc bullets from 4.md/5.md (not executable utterances)."""
    if not user or len(user) < 2:
        return True
    if "**" in user or "拼写错误" in user:
        return True
    if user.strip() in ("切换", "/new", "/new`"):
        return True
    if " / " in user and ("“" in user or "**" in user):
        return True
    if user.startswith("**") or user.endswith("**："):
        return True
    if user.count("“") >= 2 and " / " in user:
        return True
    if user.startswith("“") and "（" in user:
        return True
    return False


def _norm_user(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t.strip("「」\"' `")


def _existing_users() -> set[str]:
    if not EXISTING_PATH.is_file():
        return set()
    data = yaml.safe_load(EXISTING_PATH.read_text(encoding="utf-8"))
    return {
        _norm_user(str(row.get("user") or "")).lower()
        for row in (data.get("utterance_catalog") or [])
        if row.get("user")
    }


def _infer_kind(user: str, category: str) -> str:
    u = user.strip()
    if u.startswith("/"):
        return "detail" if u.startswith("/详细") else "command"
    if any(x in u for x in ("详细", "完整报告", "详细信息")) and "删除" not in u[:6]:
        if u in ("详细", "看一下详细", "查看详细", "完整报告") or u.endswith("详细信息"):
            return "detail"
    if any(k in u for k in ("切换", "切到", "切回", "换项目")) and "文件" not in u:
        if "继续" in u or "刚才" in u:
            return "llm"
        return "command"
    if any(k in u for k in ("在哪个项目", "什么项目", "哪个项目", "当前项目")):
        return "command"
    return "llm"


def _infer_fixture(category: str, user: str) -> str:
    u = user
    if "演示" in u:
        return "dual"
    if "novel-factory" in u or "workflow_state" in u or "小说工厂" in u:
        return "lingwen_workflow"
    if category in ("project_session", "general") and ("切换" in u or "项目" in u):
        return "dual"
    return "lingwen"


def _infer_script(kind: str, category: str, user: str) -> str | None:
    if kind in ("command", "detail"):
        return None
    u = user.lower()
    if any(x in u for x in ("/etc/passwd", "api key", "apikey", "删库", "rm -rf", "密钥")):
        return "refuse_unsafe"
    if category == "safety_boundary":
        return "refuse_unsafe"
    if "报错" in user or "出错" in user:
        return "error_guide"
    if "记住" in user or "记忆" in user and "待审" not in user:
        return "project_memory_answer"
    if "刚才" in user and ("聊" in user or "说" in user):
        return "deny_prior_details"
    if "继续" in user:
        return "continue_delete_hello"
    if "干什么" in user or "你能" in user or "功能" in user:
        return "capabilities"
    if "介绍" in user and "自己" in user:
        return "greeting"
    if "委派" in user or "代理" in user:
        if "删" in user:
            return "generic_delegate_delete"
        if "测试" in user or "pytest" in u:
            return "delegate_pytest"
        if "审核" in user:
            return "delegate_review"
        if "检查" in user or "是否存在" in user:
            return "dev_readonly_smoke"
        return "generic_delegate_write"
    if "workflow_state" in u or "workflow state" in u:
        return "read_workflow_state"
    if "读" in user or "列出" in user or "目录" in user or "readme" in u:
        return "read_readme"
    if "project.yaml" in u or "配置" in user and "看" in user:
        return "read_readme"
    if "方案" in user or "先别写" in user:
        return "plan_only"
    return "generic_ack"


def _infer_expect(kind: str, category: str, user: str) -> dict[str, Any]:
    if kind == "command":
        u = user
        if "/新对话" in u or "新会话" in u or "新对话" in u:
            return {"response_contains_any": ["清空", "上下文", "新对话"]}
        if "切换" in u or "切到" in u or "切回" in u:
            return {"response_contains_any": ["切换", "项目"]}
        if "/状态" in u or u == "状态" or "状态" in u[:4]:
            return {"response_contains_any": ["Butler", "当前项目", "项目"]}
        if "/诊断" in u or "/health" in u:
            return {"response_contains": ["Butler 诊断"]}
        if "记忆待审" in u:
            return {"response_contains_any": ["待审", "记忆", "Pending", "没有待批准"]}
        if "记忆图谱" in u:
            return {"response_contains_any": ["记忆", "图谱", "三元组"]}
        if "/定时" in u:
            return {"response_contains_any": ["定时任务", "runtime", "jobs.yaml", "任务"]}
        if "/工作流" in u:
            return {"response_contains_any": ["工作流", "novel-factory", "用法"]}
        if "/项目" in u:
            return {"response_contains_any": ["项目", "灵文", "演示"]}
        if "项目" in u:
            return {"response_contains_any": ["灵文", "当前项目", "项目"]}
    if kind == "detail":
        return {
            "no_llm": True,
            "setup": "cached_report_delete",
            "response_contains_any": ["【本报告任务】", "暂无", "变更"],
        }
    if user.strip().startswith("/运行") or user.strip().startswith("/run-job"):
        return {
            "response_contains_any": ["运行", "任务", "job", "定时", "执行", "未找到", "不存在", "Butler"],
        }
    script = _infer_script(kind, category, user) or ""
    if script == "read_workflow_state":
        return {"response_contains_any": ["phase", "step", "workflow", "draft", "outline", "状态"]}
    if script == "error_guide":
        return {"response_contains_any": ["报错", "诊断", "栈", "/诊断", "错误", "贴"]}
    if script == "dev_readonly_smoke":
        return {"response_contains_any": ["代理", "文件", "存在", "检查", "开发", "docs"]}
    if script == "plan_only":
        return {"response_contains_any": ["方案", "先", "确认", "需求", "委派", "列"]}
    if "refuse" in script:
        return {"response_contains_any": ["拒绝", "不能", "无法", "不允许", "安全", "路径"]}
    if "delegate" in script:
        return {
            "response_contains_any": ["代理", "已完成", "委派", "删除", "详细", "开发"],
        }
    if "deny_prior" in script:
        return {
            "response_excludes": ["wechat-smoke"],
            "response_contains_any": ["清空", "无法", "复述", "新对话"],
        }
    if "read" in script:
        return {"response_contains_any": ["README", "docs", "文件", "目录", "read"]}
    return {"response_contains_any": ["好的", "完成", "代理", "项目", "灵文", "莎丽", "厂长"]}


def _build_entry(
    *,
    ref_id: str,
    user: str,
    category: str,
    source: str,
    variants: list[str] | None = None,
) -> dict[str, Any]:
    kind = _infer_kind(user, category)
    expect = dict(_infer_expect(kind, category, user))
    setup = expect.pop("setup", None)
    entry: dict[str, Any] = {
        "id": ref_id,
        "user": user,
        "category": category,
        "fixture": _infer_fixture(category, user),
        "kind": kind,
        "source_file": source,
        "tier": "reference",
        "quality": "smoke",
        "runner": "reference_smoke",
    }
    script = _infer_script(kind, category, user)
    if script:
        entry["script"] = script
    if setup:
        entry["setup"] = setup
    if expect:
        entry["expect"] = expect
    if variants:
        entry["variants"] = variants[:6]
    return entry


def _parse_yaml_blocks(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in re.findall(r"```yaml\s*(.*?)```", text, flags=re.S | re.I):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("user"):
                    rows.append(item)
    return rows


def _section_category(line: str) -> str:
    for prefix, cat in _SECTION_CAT.items():
        if prefix in line or line.strip().startswith(prefix.rstrip(".")):
            return cat
    if "项目与会话" in line:
        return "project_session"
    if "只读" in line:
        return "read_only"
    if "委派" in line or "文件" in line:
        return "delegate_file"
    if "报告" in line or "详细" in line:
        return "detail_report"
    if "记忆" in line or "运维" in line:
        return "memory_ops"
    if "工作流" in line or "定时" in line:
        return "workflow_runtime"
    if "异常" in line or "边界" in line:
        return "safety_boundary"
    return "general"


def main() -> None:
    seen = _existing_users()
    entries: list[dict[str, Any]] = []
    seq = 0

    def add(
        user: str,
        category: str,
        source: str,
        *,
        ref_id: str = "",
        variants: list[str] | None = None,
    ) -> None:
        nonlocal seq
        user = _norm_user(user)
        if not user or len(user) < 2 or _is_doc_noise(user):
            return
        if user.lower() in seen:
            return
        seen.add(user.lower())
        seq += 1
        rid = ref_id if ref_id.startswith("REF-") else f"REF-{seq:04d}"
        entries.append(
            _build_entry(
                ref_id=rid,
                user=user,
                category=category,
                source=source,
                variants=variants,
            )
        )

    # 1.md — structured tables + A–G bullets
    text1 = (REF_DIR / "1.md").read_text(encoding="utf-8")
    for m in re.finditer(
        r"\|\s*(REAL-\d{8}-\d{3})\s*\|\s*([^|]+)\|",
        text1,
    ):
        rid = m.group(1).replace("REAL-", "REF-")
        user = _norm_user(m.group(2))
        add(user, "catalog_table", "reference/用户语料/1.md", ref_id=rid)

    section = "general"
    for line in text1.splitlines():
        if line.startswith("## "):
            section = _section_category(line)
        if line.strip().startswith("- "):
            add(line.strip()[2:], section, "reference/用户语料/1.md")

    # 2.md — primary YAML blocks (~110)
    text2 = (REF_DIR / "2.md").read_text(encoding="utf-8")
    for item in _parse_yaml_blocks(text2):
        uid = str(item.get("id") or "").replace("REAL-", "REF-")
        user = _norm_user(str(item.get("user") or ""))
        cat = str(item.get("category") or "yaml_block")
        variants = [
            _norm_user(str(v))
            for v in (item.get("variants") or [])
            if isinstance(v, str) and _norm_user(str(v))
        ]
        add(user, cat, "reference/用户语料/2.md", ref_id=uid, variants=variants or None)

    # 3.md — scenario tables (first column = user utterance)
    text3 = (REF_DIR / "3.md").read_text(encoding="utf-8")
    for line in text3.splitlines():
        if not line.startswith("|") or "---" in line or "用户原话" in line:
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) < 2:
            continue
        user = _norm_user(cols[0])
        if user.startswith("REAL-") or user in ("A", "B", "C", "D", "E", "F", "G"):
            continue
        cat = cols[1] if len(cols) > 1 else "table3"
        add(user, f"scenario_{cat}", "reference/用户语料/3.md")

    # 4.md / 5.md — bullet lists only (scenario ideas, deduped)
    for name in ("4.md", "5.md"):
        text = (REF_DIR / name).read_text(encoding="utf-8")
        section = "general"
        for line in text.splitlines():
            if line.startswith("###"):
                section = _section_category(line)
            if line.startswith("## "):
                section = _section_category(line)
            s = line.strip()
            if s.startswith("- "):
                body = _norm_user(s[2:])
                if 3 <= len(body) <= 120:
                    add(body, section, f"reference/用户语料/{name}")
            if s.startswith("* "):
                body = _norm_user(s[2:])
                if 3 <= len(body) <= 120:
                    add(body, section, f"reference/用户语料/{name}")

    doc = {
        "meta": {
            "version": "2026-05-24-reference-ingest-r2",
            "source_dir": "reference/用户语料",
            "source_files": ["1.md", "2.md", "3.md", "4.md", "5.md"],
            "entry_count": len(entries),
            "ingest_script": "scripts/ingest_reference_user_corpus.py",
        },
        "utterance_catalog": entries,
    }
    OUT_PATH.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} entries → {OUT_PATH}")


if __name__ == "__main__":
    main()
