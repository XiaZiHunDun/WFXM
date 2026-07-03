"""Extension Verify (L1): golden MCP calls + secret contracts."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.mcp.config import mcp_enabled, mcp_sdk_available
from butler.mcp.extension_manifest import (
    ExtensionManifest,
    check_secret_contracts,
    env_secret_value,
    get_manifest,
    load_all_manifests,
)

_VERIFY_CACHE = Path.home() / ".butler" / "extension-verify-cache.json"


@dataclass
class CaseResult:
    tool: str
    ok: bool
    detail: str = ""
    skipped: bool = False


@dataclass
class VerifyReport:
    ext_id: str
    ok: bool
    at: str = ""
    cases: list[CaseResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_tool_payload(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _count_items(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if "repo_count" in payload:
            return int(payload.get("repo_count") or 0)
        if "issue_count" in payload:
            return int(payload.get("issue_count") or 0)
        if "repos" in payload and isinstance(payload["repos"], list):
            return len(payload["repos"])
        if "issues" in payload and isinstance(payload["issues"], list):
            return len(payload["issues"])
        if payload.get("code") == "MCP_OK":
            return 1
    return 0


def _field_present(payload: Any, field_name: str) -> bool:
    if isinstance(payload, list) and payload:
        sample = payload[0]
        return isinstance(sample, dict) and field_name in sample
    if isinstance(payload, dict):
        if field_name in payload:
            return True
        for key in ("repos", "issues"):
            items = payload.get(key)
            if isinstance(items, list) and items:
                return isinstance(items[0], dict) and field_name in items[0]
    return False


def run_golden_case(
    manifest: ExtensionManifest,
    tool_name: str,
    golden_args: dict[str, Any],
    *,
    expect_min_items: int = 0,
    expect_fields: tuple[str, ...] = (),
    session_key: str = "extension-verify",
) -> CaseResult:
    if not mcp_enabled():
        return CaseResult(tool=tool_name, ok=False, skipped=True, detail="MCP disabled")
    if not mcp_sdk_available():
        return CaseResult(tool=tool_name, ok=False, skipped=True, detail="MCP SDK missing")
    for contract in manifest.secrets:
        if not env_secret_value(contract):
            return CaseResult(
                tool=tool_name,
                ok=False,
                skipped=True,
                detail=f"{contract.env} unset",
            )
    from butler.mcp.extension_verify_ops import dispatch_golden_tool_safe

    ok, raw, err = dispatch_golden_tool_safe(tool_name, golden_args)
    if not ok:
        return CaseResult(tool=tool_name, ok=False, detail=err or "dispatch failed")
    if not raw or '"ok": false' in raw.replace(" ", "").lower():
        return CaseResult(tool=tool_name, ok=False, detail=(raw or "empty")[:200])
    payload = _parse_tool_payload(raw)
    count = _count_items(payload)
    if count < expect_min_items:
        return CaseResult(
            tool=tool_name,
            ok=False,
            detail=f"item_count={count} < expect_min_items={expect_min_items}",
        )
    for fld in expect_fields:
        if not _field_present(payload, fld):
            return CaseResult(tool=tool_name, ok=False, detail=f"missing field {fld}")
    return CaseResult(tool=tool_name, ok=True, detail=f"items={count}")


def verify_manifest(
    manifest: ExtensionManifest,
    *,
    workspace: Path | str | None = None,
    session_key: str = "extension-verify",
    run_golden: bool = True,
) -> VerifyReport:
    report = VerifyReport(ext_id=manifest.id, ok=True, at=_now_iso())
    report.errors.extend(check_secret_contracts(manifest))
    if manifest.mcp_enabled_required and not mcp_enabled():
        report.warnings.append("BUTLER_MCP_ENABLED not 1")
    if not run_golden:
        report.ok = not report.errors
        return report
    if report.errors:
        report.ok = False
        return report
    for tool in manifest.tools:
        if tool.golden is None or tool.golden.skip:
            continue
        result = run_golden_case(
            manifest,
            tool.registered,
            tool.golden.args,
            expect_min_items=tool.golden.expect_min_items,
            expect_fields=tool.golden.expect_fields,
            session_key=session_key,
        )
        report.cases.append(result)
        if result.skipped:
            report.warnings.append(f"{tool.registered}: {result.detail}")
        elif not result.ok:
            report.errors.append(f"{tool.registered}: {result.detail}")
    report.ok = not report.errors
    return report


def verify_extension(
    ext_id: str,
    *,
    workspace: Path | str | None = None,
    session_key: str = "extension-verify",
    run_golden: bool = True,
) -> VerifyReport:
    manifest = get_manifest(ext_id, workspace)
    if manifest is None:
        return VerifyReport(
            ext_id=ext_id,
            ok=False,
            at=_now_iso(),
            errors=[f"manifest not found for {ext_id}"],
        )
    return verify_manifest(
        manifest,
        workspace=workspace,
        session_key=session_key,
        run_golden=run_golden,
    )


def write_verify_cache(reports: dict[str, VerifyReport]) -> Path:
    _VERIFY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v.to_dict() for k, v in reports.items()}
    _VERIFY_CACHE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return _VERIFY_CACHE


def read_verify_cache() -> dict[str, Any]:
    from butler.mcp.extension_verify_ops import read_verify_cache_dict_safe

    return read_verify_cache_dict_safe(_VERIFY_CACHE)


def extension_verify_status_lines() -> list[str]:
    cache = read_verify_cache()
    if not cache:
        manifests = load_all_manifests()
        if not manifests:
            return []
        return [
            "Extension Verify: 未缓存（运行 bash scripts/butler-extension-verify.sh）"
        ]
    lines = ["Extension Verify:"]
    for ext_id, entry in sorted(cache.items()):
        if not isinstance(entry, dict):
            continue
        mark = "ok" if entry.get("ok") else "fail"
        at = str(entry.get("at") or "")[:19]
        case_n = len(entry.get("cases") or [])
        lines.append(f"  - {ext_id} [{mark}] cases={case_n} @ {at}")
    return lines


def verify_for_server_id(
    server_id: str,
    *,
    workspace: Path | str | None = None,
    run_golden: bool = True,
) -> VerifyReport | None:
    from butler.mcp.extension_manifest import get_manifest_by_server_id

    manifest = get_manifest_by_server_id(server_id, workspace)
    if manifest is None:
        return None
    return verify_manifest(manifest, workspace=workspace, run_golden=run_golden)


def format_post_install_verify_hint(report: VerifyReport, manifest: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "extension_id": manifest.id,
        "verify_ok": report.ok,
        "acceptance_phrases": list(manifest.verify_phrases),
    }
    if report.errors:
        out["errors"] = list(report.errors)
    if report.warnings:
        out["warnings"] = list(report.warnings)
    sync_scripts = [
        str(c.sync_script).strip()
        for c in manifest.secrets
        if getattr(c, "sync_script", "")
    ]
    if sync_scripts:
        out["sync_hint"] = f"bash {sync_scripts[0]}"
    out["verify_cmd"] = f"bash scripts/butler-extension-verify.sh {manifest.id}"
    return out


def verify_all_extensions(
    *,
    workspace: Path | str | None = None,
    session_key: str = "extension-verify",
    run_golden: bool = True,
) -> dict[str, VerifyReport]:
    manifests = load_all_manifests(workspace)
    reports: dict[str, VerifyReport] = {}
    for manifest in manifests.values():
        reports[manifest.id] = verify_manifest(
            manifest,
            workspace=workspace,
            session_key=session_key,
            run_golden=run_golden,
        )
    if reports:
        write_verify_cache(reports)
    return reports
