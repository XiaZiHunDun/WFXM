"""Tests for butler.tools.multimodal_tools — image gen and TTS tool wrappers."""

from __future__ import annotations

import json
import pytest


class TestGenerateImage:
    def test_disabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_IMAGE_GENERATION", "0")
        from butler.tools.multimodal_tools import tool_generate_image

        data = json.loads(tool_generate_image(prompt="a cat"))
        assert "error" in data
        assert "disabled" in data["error"]

    def test_empty_prompt(self, monkeypatch):
        monkeypatch.setenv("BUTLER_IMAGE_GENERATION", "1")
        from butler.tools.multimodal_tools import tool_generate_image

        data = json.loads(tool_generate_image(prompt=""))
        assert "error" in data

    def test_no_api_key(self, monkeypatch):
        monkeypatch.setenv("BUTLER_IMAGE_GENERATION", "1")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
        from butler.tools.multimodal_tools import tool_generate_image

        data = json.loads(tool_generate_image(prompt="a cat"))
        assert "error" in data


class TestSynthesizeSpeech:
    def test_disabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TTS", "0")
        from butler.tools.multimodal_tools import tool_synthesize_speech

        data = json.loads(tool_synthesize_speech(text="hello"))
        assert "error" in data

    def test_empty_text(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TTS", "1")
        from butler.tools.multimodal_tools import tool_synthesize_speech

        data = json.loads(tool_synthesize_speech(text=""))
        assert "error" in data

    def test_text_too_long(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TTS", "1")
        from butler.tools.multimodal_tools import tool_synthesize_speech

        data = json.loads(tool_synthesize_speech(text="x" * 6000))
        assert "error" in data
        assert "too long" in data["error"]

    def test_no_api_key(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TTS", "1")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
        from butler.tools.multimodal_tools import tool_synthesize_speech

        data = json.loads(tool_synthesize_speech(text="hello"))
        assert "error" in data


class TestRegistration:
    def test_registers_both_tools(self):
        registered = {}
        def fake_register(name, description, schema, handler, toolset="default"):
            registered[name] = {"schema": schema, "toolset": toolset}

        from butler.tools.multimodal_tools import register_multimodal_tools
        register_multimodal_tools(fake_register)

        assert "generate_image" in registered
        assert "synthesize_speech" in registered
        assert registered["generate_image"]["toolset"] == "multimodal"
