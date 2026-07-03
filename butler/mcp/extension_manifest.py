"""Load extension manifests from .butler/extensions (L0 SSOT)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_MANIFEST_NAME = "manifest.yaml"


@dataclass(frozen=True)
class SecretContract:
    env: str
    alt_envs: tuple[str, ...] = ()
    secrets_yaml_key: str = ""
    require_in_process_env: bool = False
    sync_script: str = ""
    severity: str = "error"


@dataclass(frozen=True)
class GoldenCase:
    args: dict[str, Any]
    expect_min_items: int = 0
    expect_fields: tuple[str, ...] = ()
    skip: bool = False


@dataclass(frozen=True)
class IntentRule:
    kind: str
    patterns: tuple[str, ...] = ()
    fallback_keywords: tuple[str, ...] = ()
    server_id: str = ""
    enabled_env: str = ""
    default_enabled: bool = True


@dataclass(frozen=True)
class ToolManifest:
    registered: str
    openapi_tool: str = ""
    aliases: tuple[str, ...] = ()
    grounding_kind: str = ""
    direct_reply: bool = False
    golden: GoldenCase | None = None


@dataclass(frozen=True)
class ExtensionManifest:
    id: str
    ext_id: str
    title: str
    server_id: str
    path: Path
    mcp_enabled_required: bool = False
    secrets: tuple[SecretContract, ...] = ()
    tools: tuple[ToolManifest, ...] = ()
    preflight_script: str = ""
    verify_phrases: tuple[str, ...] = ()
    grounding_config: dict[str, str] = field(default_factory=dict)
    intent_rules: tuple[IntentRule, ...] = ()


def _workspace_root(workspace: Path | str | None = None) -> Path:
    if workspace:
        return Path(workspace).expanduser().resolve()
    return Path.cwd().resolve()


def extension_search_roots(workspace: Path | str | None = None) -> list[Path]:
    ws = _workspace_root(workspace)
    home = Path.home()
    roots: list[Path] = []
    for base in (ws / ".butler" / "extensions", home / ".butler" / "extensions"):
        if base.is_dir():
            roots.append(base)
    return roots


def _parse_secret(raw: dict[str, Any]) -> SecretContract:
    alt = raw.get("alt_envs") or []
    return SecretContract(
        env=str(raw.get("env") or "").strip(),
        alt_envs=tuple(str(x).strip() for x in alt if str(x).strip()),
        secrets_yaml_key=str(raw.get("secrets_yaml_key") or raw.get("env") or "").strip(),
        require_in_process_env=bool(raw.get("require_in_process_env")),
        sync_script=str(raw.get("sync_script") or "").strip(),
        severity=str(raw.get("severity") or "error").strip().lower(),
    )


def _parse_golden(raw: dict[str, Any] | None) -> GoldenCase | None:
    if not isinstance(raw, dict):
        return None
    fields = raw.get("expect_fields") or []
    return GoldenCase(
        args=dict(raw.get("args") or {}),
        expect_min_items=int(raw.get("expect_min_items") or 0),
        expect_fields=tuple(str(x) for x in fields),
        skip=bool(raw.get("skip")),
    )


def _parse_intent(raw: dict[str, Any], *, server_id: str) -> IntentRule:
    patterns = raw.get("patterns") or []
    keywords = raw.get("fallback_keywords") or []
    return IntentRule(
        kind=str(raw.get("kind") or "").strip(),
        patterns=tuple(str(p) for p in patterns if str(p).strip()),
        fallback_keywords=tuple(str(k) for k in keywords if str(k).strip()),
        server_id=str(raw.get("server_id") or server_id).strip(),
        enabled_env=str(raw.get("enabled_env") or "").strip(),
        default_enabled=bool(raw.get("default_enabled", True)),
    )


def _parse_tool(raw: dict[str, Any]) -> ToolManifest:
    grounding = raw.get("grounding") or {}
    aliases = raw.get("aliases") or []
    return ToolManifest(
        registered=str(raw.get("registered") or "").strip(),
        openapi_tool=str(raw.get("openapi_tool") or "").strip(),
        aliases=tuple(str(x).strip() for x in aliases if str(x).strip()),
        grounding_kind=str(grounding.get("kind") or "").strip(),
        direct_reply=bool(grounding.get("direct_reply")),
        golden=_parse_golden(raw.get("golden")),
    )


def _parse_manifest(path: Path, data: dict[str, Any]) -> ExtensionManifest | None:
    ext_id = str(data.get("id") or path.parent.name).strip()
    if not ext_id:
        return None
    secrets_raw = data.get("secrets") or []
    tools_raw = data.get("tools") or []
    phrases = data.get("verify_phrases") or []
    grounding_raw = data.get("grounding") or {}
    intents_raw = grounding_raw.get("intents") or []
    server_id = str(data.get("server_id") or "").strip()
    return ExtensionManifest(
        id=ext_id,
        ext_id=str(data.get("ext_id") or ext_id).strip(),
        title=str(data.get("title") or ext_id).strip(),
        server_id=server_id,
        path=path,
        mcp_enabled_required=bool(data.get("mcp_enabled_required")),
        secrets=tuple(_parse_secret(s) for s in secrets_raw if isinstance(s, dict)),
        tools=tuple(_parse_tool(t) for t in tools_raw if isinstance(t, dict)),
        preflight_script=str(data.get("preflight_script") or "").strip(),
        verify_phrases=tuple(str(p) for p in phrases if str(p).strip()),
        grounding_config=dict(grounding_raw),
        intent_rules=tuple(
            _parse_intent(i, server_id=server_id)
            for i in intents_raw
            if isinstance(i, dict)
        ),
    )


def load_manifest_file(path: Path) -> ExtensionManifest | None:
    from butler.mcp.extension_manifest_ops import load_yaml_mapping_safe

    data = load_yaml_mapping_safe(path)
    if data is None:
        return None
    return _parse_manifest(path, data)


def load_all_manifests(workspace: Path | str | None = None) -> dict[str, ExtensionManifest]:
    """Later roots override earlier on duplicate id."""
    out: dict[str, ExtensionManifest] = {}
    for root in extension_search_roots(workspace):
        for path in sorted(root.glob(f"*/{_MANIFEST_NAME}")):
            manifest = load_manifest_file(path)
            if manifest is not None:
                out[manifest.id] = manifest
    return out


def get_manifest_by_server_id(
    server_id: str,
    workspace: Path | str | None = None,
) -> ExtensionManifest | None:
    key = str(server_id or "").strip().lower()
    if not key:
        return None
    for manifest in load_all_manifests(workspace).values():
        if manifest.server_id.lower() == key:
            return manifest
    return None


def load_intent_rules(workspace: Path | str | None = None) -> list[IntentRule]:
    rules: list[IntentRule] = []
    for manifest in load_all_manifests(workspace).values():
        rules.extend(manifest.intent_rules)
    return rules


def tools_for_grounding_kind(
    kind: str,
    workspace: Path | str | None = None,
) -> list[str]:
    key = str(kind or "").strip()
    names: list[str] = []
    for manifest in load_all_manifests(workspace).values():
        for tool in manifest.tools:
            if tool.grounding_kind == key and tool.direct_reply:
                names.append(tool.registered)
    return names


def get_manifest(ext_id: str, workspace: Path | str | None = None) -> ExtensionManifest | None:
    key = str(ext_id or "").strip()
    if not key:
        return None
    manifests = load_all_manifests(workspace)
    if key in manifests:
        return manifests[key]
    for manifest in manifests.values():
        if manifest.ext_id == key:
            return manifest
    return None


def build_alias_map(workspace: Path | str | None = None) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for manifest in load_all_manifests(workspace).values():
        for tool in manifest.tools:
            for alias in tool.aliases:
                aliases[alias] = tool.registered
    return aliases


def resolve_tool_alias(name: str, workspace: Path | str | None = None) -> str:
    key = str(name or "").strip()
    return build_alias_map(workspace).get(key, key)


def read_secrets_yaml_value(key: str, secrets_path: Path | None = None) -> str:
    path = secrets_path or Path(
        os.getenv("BUTLER_SECRETS_PATH", str(Path.home() / ".butler" / "secrets.yaml"))
    )
    if not path.is_file():
        return ""
    from butler.mcp.extension_manifest_ops import load_yaml_mapping_safe

    data = load_yaml_mapping_safe(path)
    if data is None:
        return ""
    val = data.get(key)
    if val is None:
        return ""
    from butler.config_secrets_crypto import decrypt_secret_value

    return decrypt_secret_value(str(val)).strip()


def env_secret_value(contract: SecretContract) -> str:
    for key in (contract.env, *contract.alt_envs):
        val = os.getenv(key, "").strip()
        if val:
            return val
    if contract.secrets_yaml_key:
        return read_secrets_yaml_value(contract.secrets_yaml_key)
    return ""


def check_secret_contracts(
    manifest: ExtensionManifest,
    *,
    secrets_path: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    for contract in manifest.secrets:
        if not contract.env:
            continue
        in_env = any(os.getenv(k, "").strip() for k in (contract.env, *contract.alt_envs))
        in_secrets = bool(
            contract.secrets_yaml_key
            and read_secrets_yaml_value(contract.secrets_yaml_key, secrets_path)
        )
        if not in_env and not in_secrets:
            errors.append(f"{contract.env} missing (secrets.yaml and process env)")
            continue
        if contract.require_in_process_env and not in_env:
            hint = contract.sync_script or "sync secrets to process env"
            if hint and not hint.startswith("bash "):
                hint = f"bash {hint}"
            errors.append(
                f"{contract.env} in secrets but not process env — run: {hint}"
            )
    return errors
