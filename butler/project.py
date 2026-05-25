"""Typed access to Butler project definitions (``project.yaml``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from butler.config import ModelConfig, get_butler_settings


def _parse_tool_modes(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, val in raw.items():
        role = str(key or "").strip().lower()
        if not role or not isinstance(val, list):
            continue
        names = [str(n).strip() for n in val if str(n).strip()]
        if names:
            out[role] = names
    return out


@dataclass
class Project:
    """Single Butler project anchored at a ``project.yaml`` on disk."""

    name: str
    type: str
    description: str
    status: str = "active"
    pack: str = ""
    lifecycle: str = ""
    lead: bool | None = None
    tenant: str = ""
    workspace: Path = field(default_factory=lambda: Path("."))
    models: dict[str, ModelConfig] = field(default_factory=dict)
    workflows: list[Any] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    worktree: str = ""
    design_preset: str = ""
    tool_modes: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()

    @classmethod
    def from_yaml(cls, path: Path) -> Project:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        ws = path.parent.resolve()
        models_raw = data.get("models", {}) or {}
        models = {str(k): ModelConfig.from_dict(v) for k, v in models_raw.items()} if models_raw else {}

        from butler.tenant import normalize_tenant_id

        tenant_raw = data.get("tenant")
        tenant = "" if tenant_raw is None else normalize_tenant_id(str(tenant_raw))

        status = str(data.get("status", "active"))
        lifecycle = str(data.get("lifecycle", "") or "").strip()
        if not lifecycle and status.lower() in ("complete", "completed", "archived"):
            lifecycle = "complete"
        elif not lifecycle:
            lifecycle = "active"

        lead_raw = data.get("lead")
        lead: bool | None
        if lead_raw is None:
            lead = None
        else:
            lead = bool(lead_raw)

        return cls(
            name=str(data.get("name", ws.name)),
            type=str(data.get("type", "software")),
            description=str(data.get("description", "")),
            status=status,
            pack=str(data.get("pack", "") or "").strip(),
            lifecycle=lifecycle,
            lead=lead,
            tenant=tenant,
            workspace=ws,
            models=models,
            workflows=list(data.get("workflows") or []),
            tools=list(data.get("tools") or []),
            worktree=str(data.get("worktree") or "").strip(),
            design_preset=str(data.get("design_preset") or "").strip(),
            tool_modes=_parse_tool_modes(data.get("tool_modes")),
        )

    def resolve_model(self, role: str, runtime_override: ModelConfig | None = None) -> ModelConfig:
        """Effective merge: system → global YAML → project.yaml → runtime."""
        from butler.model_resolve import resolve_effective_model

        merged = resolve_effective_model(role, project=self).config
        return merged.merge_with(runtime_override)

    def set_model(self, role: str, config: ModelConfig) -> None:
        self.models[role] = config
        self.save()

    def to_dict(self) -> dict[str, Any]:
        root = get_butler_settings().projects_dir.parent.resolve()
        try:
            ws_display = self.workspace.relative_to(root)
        except ValueError:
            ws_display = self.workspace
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "status": self.status,
            "workspace": str(ws_display).replace("\\", "/"),
        }
        if self.pack:
            d["pack"] = self.pack
        if self.lifecycle:
            d["lifecycle"] = self.lifecycle
        if self.lead is not None:
            d["lead"] = self.lead
        if self.tenant and self.tenant != "default":
            d["tenant"] = self.tenant

        if self.models:
            d["models"] = {k: v.to_dict() for k, v in self.models.items() if not v.is_empty()}
        if self.workflows:
            d["workflows"] = self.workflows
        if self.tools:
            d["tools"] = self.tools
        if self.worktree:
            d["worktree"] = self.worktree
        if self.design_preset:
            d["design_preset"] = self.design_preset
        if self.tool_modes:
            d["tool_modes"] = dict(self.tool_modes)
        return d

    def save(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        config_path = self.workspace / "project.yaml"

        payload = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "status": self.status,
        }
        if self.pack:
            payload["pack"] = self.pack
        if self.lifecycle:
            payload["lifecycle"] = self.lifecycle
        if self.lead is not None:
            payload["lead"] = self.lead
        if self.tenant and self.tenant != "default":
            payload["tenant"] = self.tenant
        if self.models:
            payload["models"] = {k: v.to_dict() for k, v in self.models.items() if not v.is_empty()}
        if self.workflows:
            payload["workflows"] = self.workflows
        if self.tools:
            payload["tools"] = self.tools
        if self.worktree:
            payload["worktree"] = self.worktree
        if self.design_preset:
            payload["design_preset"] = self.design_preset
        if self.tool_modes:
            payload["tool_modes"] = dict(self.tool_modes)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
