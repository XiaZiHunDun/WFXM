"""Phase A3: meta/workflow/confirm/gateway-queue/observation defaults relocation."""

from __future__ import annotations

import pytest

from butler.core import confirm_flags, meta_flags
from butler.defaults import env_defaults as ed
from butler.defaults import env_domains
from butler.gateway import completion_notify, queue_settings
from butler.memory import observation_store


@pytest.mark.unit
class TestEnvDefaultsPhaseA3:
    def test_meta_flags_dag_constants(self, monkeypatch):
        monkeypatch.delenv("BUTLER_WORKFLOW_MAX_PARALLEL", raising=False)
        assert meta_flags.MAX_DAG_NODES == ed.WORKFLOW_MAX_DAG_NODES == 50
        assert meta_flags.MAX_DAG_PARALLEL == ed.WORKFLOW_MAX_DAG_PARALLEL == 5
        assert meta_flags.workflow_max_parallel_default() == 5

    def test_confirm_schema_repair_max(self, monkeypatch):
        monkeypatch.delenv("BUTLER_OUTPUT_SCHEMA_REPAIR_MAX", raising=False)
        assert confirm_flags.output_schema_repair_max_rounds() == ed.OUTPUT_SCHEMA_REPAIR_MAX

    def test_delegate_completion_max_each(self, monkeypatch):
        monkeypatch.delenv("BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH", raising=False)
        assert completion_notify.delegate_completion_max_each() == ed.GATEWAY_DELEGATE_COMPLETION_MAX_EACH

    def test_observation_ttl_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_OBSERVATION_TTL_DAYS", raising=False)
        assert observation_store.ObservationStore._ttl_days() == ed.OBSERVATION_TTL_DAYS

    def test_gateway_queue_defaults(self, monkeypatch):
        monkeypatch.delenv("BUTLER_GATEWAY_QUEUE_MODE", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_QUEUE_CAP", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_QUEUE_DROP", raising=False)
        assert queue_settings.default_queue_mode() == ed.GATEWAY_DEFAULT_QUEUE_MODE
        assert queue_settings.queue_cap() == ed.GATEWAY_QUEUE_CAP
        assert queue_settings.queue_drop_policy() == ed.GATEWAY_DEFAULT_QUEUE_DROP

    def test_env_domains_registry(self):
        assert len(env_domains.ENV_DOMAINS) >= 12
        assert env_domains.domain_by_id("meta") is not None
        assert env_domains.domain_by_id("unknown") is None
        meta = env_domains.domain_by_id("meta")
        assert meta is not None
        assert "BUTLER_WORKFLOW_MAX_PARALLEL" in meta.env_vars
