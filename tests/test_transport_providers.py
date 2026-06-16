"""L1 unit tests for butler.transport.providers."""

import os

import pytest

import butler.transport.providers as providers_mod
from butler.transport.providers import ProviderProfile, get_provider, list_providers, register_provider


@pytest.fixture(autouse=True)
def restore_provider_registry():
    """Snapshot and restore global provider registry between tests."""
    orig_registry = dict(providers_mod._REGISTRY)
    orig_aliases = dict(providers_mod._ALIASES)
    providers_mod._REGISTRY.clear()
    providers_mod._ALIASES.clear()
    providers_mod._register_builtin()
    yield
    providers_mod._REGISTRY.clear()
    providers_mod._REGISTRY.update(orig_registry)
    providers_mod._ALIASES.clear()
    providers_mod._ALIASES.update(orig_aliases)


@pytest.mark.unit
class TestListProviders:
    def test_returns_at_least_nine_providers(self):
        names = {p.name for p in list_providers()}
        assert len(names) >= 9
        assert "deepseek" in names
        assert "minimax" in names
        assert "openai" in names


@pytest.mark.unit
class TestGetProvider:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("deepseek", "deepseek"),
            ("minimax", "minimax"),
            ("openai", "openai"),
            ("anthropic", "anthropic"),
            ("qwen", "qwen"),
            ("openrouter", "openrouter"),
            ("siliconflow", "siliconflow"),
            ("zhipu", "zhipu"),
        ],
    )
    def test_builtin_has_correct_fields(self, name, expected):
        p = get_provider(name)
        assert p is not None
        assert p.name == expected
        assert p.api_mode
        assert p.base_url
        assert p.env_vars

    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("deepseek-chat", "deepseek"),
            ("mini-max", "minimax"),
            ("gpt", "openai"),
            ("claude", "anthropic"),
            ("tongyi", "qwen"),
            ("silicon", "siliconflow"),
            ("glm", "zhipu"),
        ],
    )
    def test_alias_resolution(self, alias, canonical):
        p = get_provider(alias)
        assert p is not None
        assert p.name == canonical

    def test_none_returns_none(self):
        assert get_provider(None) is None  # type: ignore[arg-type]

    def test_unknown_returns_none(self):
        assert get_provider("not-a-real-provider-xyz") is None


@pytest.mark.unit
class TestResolveApiKey:
    def test_from_env_var(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
        p = get_provider("deepseek")
        assert p is not None
        assert p.resolve_api_key() == "sk-test-deepseek"

    def test_missing_env_var_returns_none(self, monkeypatch):
        monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
        p = get_provider("zhipu")
        assert p is not None
        assert p.resolve_api_key() is None


@pytest.mark.unit
class TestRegisterProvider:
    def test_custom_provider(self, restore_provider_registry):
        custom = ProviderProfile(
            name="custom-test",
            api_mode="chat_completions",
            base_url="https://custom.example/v1",
            env_vars=("CUSTOM_TEST_KEY",),
            default_model="custom-model",
        )
        register_provider(custom)
        p = get_provider("custom-test")
        assert p is not None
        assert p.base_url == "https://custom.example/v1"

    def test_reregister_overwrites(self, restore_provider_registry):
        first = ProviderProfile(name="overwrite-test", base_url="https://first.example")
        second = ProviderProfile(name="overwrite-test", base_url="https://second.example")
        register_provider(first)
        register_provider(second)
        p = get_provider("overwrite-test")
        assert p is not None
        assert p.base_url == "https://second.example"
