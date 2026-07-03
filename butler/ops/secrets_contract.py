"""Unified secrets.yaml ↔ process env contracts (G1-13)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from butler.mcp.extension_manifest import (
    ExtensionManifest,
    SecretContract,
    check_secret_contracts,
    load_all_manifests,
    read_secrets_yaml_value,
)

_CONTRACT_NAME = "secrets-contract.yaml"


@dataclass
class PlatformContract:
    id: str
    title: str
    require_any_env: tuple[str, ...] = ()
    severity: str = "error"
    when_gateway_expected: bool = False
    secrets: tuple[SecretContract, ...] = ()


@dataclass
class SecretsCheckReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extension_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "extension_ids": list(self.extension_ids),
        }


def _workspace_root(workspace: Path | str | None = None) -> Path:
    if workspace:
        return Path(workspace).expanduser().resolve()
    return Path.cwd().resolve()


def _contract_paths(workspace: Path | str | None = None) -> list[Path]:
    ws = _workspace_root(workspace)
    paths: list[Path] = []
    for base in (ws / ".butler", Path.home() / ".butler"):
        candidate = base / _CONTRACT_NAME
        if candidate.is_file():
            paths.append(candidate)
    return paths


def _parse_platform_secret(raw: dict[str, Any]) -> SecretContract:
    alt = raw.get("alt_envs") or []
    return SecretContract(
        env=str(raw.get("env") or "").strip(),
        alt_envs=tuple(str(x).strip() for x in alt if str(x).strip()),
        secrets_yaml_key=str(raw.get("secrets_yaml_key") or raw.get("env") or "").strip(),
        require_in_process_env=bool(raw.get("require_in_process_env")),
        sync_script=str(raw.get("sync_script") or "").strip(),
        severity=str(raw.get("severity") or "error").strip().lower(),
    )


def _parse_platform_contract(raw: dict[str, Any]) -> PlatformContract | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    secrets_raw = raw.get("secrets") or []
    require_any = raw.get("require_any_env") or []
    return PlatformContract(
        id=str(raw["id"]).strip(),
        title=str(raw.get("title") or raw["id"]).strip(),
        require_any_env=tuple(str(x).strip() for x in require_any if str(x).strip()),
        severity=str(raw.get("severity") or "error").strip().lower(),
        when_gateway_expected=bool(raw.get("when_gateway_expected")),
        secrets=tuple(_parse_platform_secret(s) for s in secrets_raw if isinstance(s, dict)),
    )


def load_platform_contracts(workspace: Path | str | None = None) -> list[PlatformContract]:
    out: list[PlatformContract] = []
    for path in _contract_paths(workspace):
        from butler.ops.secrets_contract_ops import load_yaml_mapping_safe

        data = load_yaml_mapping_safe(path)
        if data is None:
            continue
        for row in data.get("platform_contracts") or []:
            contract = _parse_platform_contract(row)
            if contract is not None:
                out.append(contract)
    return out


def _contract_in_env(contract: SecretContract) -> bool:
    return any(os.getenv(k, "").strip() for k in (contract.env, *contract.alt_envs))


def _check_platform_contract(
    contract: PlatformContract,
    *,
    gateway_expected: bool,
    secrets_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if contract.when_gateway_expected and not gateway_expected:
        return errors, warnings

    if contract.require_any_env:
        if not any(os.getenv(k, "").strip() for k in contract.require_any_env):
            msg = (
                f"{contract.id}: none of {', '.join(contract.require_any_env)} "
                f"in process env"
            )
            if contract.severity == "warn":
                warnings.append(msg)
            else:
                errors.append(msg)

    for secret in contract.secrets:
        if not secret.env:
            continue
        in_env = _contract_in_env(secret)
        in_secrets = bool(
            secret.secrets_yaml_key
            and read_secrets_yaml_value(secret.secrets_yaml_key, secrets_path)
        )
        if not in_env and not in_secrets:
            msg = f"{contract.id}: {secret.env} missing (secrets.yaml and process env)"
            sev = secret.severity or contract.severity or "error"
            if sev == "warn":
                warnings.append(msg)
            else:
                errors.append(msg)
            continue
        if secret.require_in_process_env and not in_env:
            hint = secret.sync_script or "sync secrets to process env"
            if hint and not hint.startswith("bash "):
                hint = f"bash {hint}"
            msg = f"{contract.id}: {secret.env} in secrets but not process env — {hint}"
            errors.append(msg)
    return errors, warnings


def check_all_secrets_contracts(
    workspace: Path | str | None = None,
    *,
    gateway_expected: bool = False,
    secrets_path: Path | None = None,
    include_extensions: bool = True,
) -> SecretsCheckReport:
    report = SecretsCheckReport(ok=True)
    manifests: dict[str, ExtensionManifest] = {}
    if include_extensions:
        manifests = load_all_manifests(workspace)
        report.extension_ids = sorted(manifests.keys())
        for manifest in manifests.values():
            report.errors.extend(check_secret_contracts(manifest, secrets_path=secrets_path))

    for platform in load_platform_contracts(workspace):
        errs, warns = _check_platform_contract(
            platform,
            gateway_expected=gateway_expected,
            secrets_path=secrets_path,
        )
        report.errors.extend(errs)
        report.warnings.extend(warns)

    report.ok = not report.errors
    return report


def detect_gateway_expected() -> bool:
    if os.getenv("BUTLER_SECRETS_GATEWAY_EXPECTED", "").strip() in ("1", "true", "yes"):
        return True
    unit = os.getenv("BUTLER_GATEWAY_SYSTEMD_UNIT", "butler-gateway.service")
    from butler.ops.secrets_contract_ops import is_systemd_unit_active_safe

    return is_systemd_unit_active_safe(unit)


def format_secrets_contract_lines(report: SecretsCheckReport) -> list[str]:
    lines = ["Secrets contract:"]
    if report.extension_ids:
        lines.append(f"  extensions: {', '.join(report.extension_ids)}")
    mark = "ok" if report.ok else "fail"
    lines.append(f"  status [{mark}] errors={len(report.errors)} warnings={len(report.warnings)}")
    for err in report.errors[:5]:
        lines.append(f"  - error: {err[:120]}")
    for warn in report.warnings[:3]:
        lines.append(f"  - warn: {warn[:120]}")
    return lines
