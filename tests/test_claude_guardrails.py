"""Credential and endpoint isolation for Setu's personal Anthropic client."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

import setu.config as config_module
import setu.llm.claude as claude_module
from setu.config import load_config
from setu.llm.claude import ClaudeClient, ClaudeError


class _RecordingAnthropic:
    """Capture constructor arguments without making a network request."""

    last_kwargs: dict | None = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs


def _config_with_personal_key(config):
    return config.model_copy(
        deep=True,
        update={"anthropic_api_key": SecretStr("personal-test-key")},
    )


def test_client_ignores_inherited_corporate_base_url(config, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.sfproxy.example")
    monkeypatch.setattr(claude_module, "Anthropic", _RecordingAnthropic)

    ClaudeClient(_config_with_personal_key(config))

    assert _RecordingAnthropic.last_kwargs == {
        "api_key": "personal-test-key",
        "base_url": "https://api.anthropic.com",
    }


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "https://gateway.sfproxy.example",
        "http://api.anthropic.com",
        "https://api.anthropic.com.evil.example",
        "https://user@api.anthropic.com",
        "https://api.anthropic.com:not-a-port",
    ],
)
def test_client_rejects_non_official_endpoint(config, monkeypatch, unsafe_url):
    monkeypatch.setattr(claude_module, "Anthropic", _RecordingAnthropic)

    with pytest.raises(ClaudeError, match="official Anthropic API"):
        ClaudeClient(_config_with_personal_key(config), base_url=unsafe_url)


def test_config_prefers_project_env_key_over_inherited_key(tmp_path, monkeypatch):
    project_root = tmp_path / "personal-setu"
    project_root.mkdir()
    (project_root / ".env").write_text("ANTHROPIC_API_KEY=personal-project-key\n")
    config_path = project_root / "config.yaml"
    config_path.write_text(
        """
paths:
  data_dir: data
  synthetic_dir: data/synthetic
  inbox_dir: data/inbox
  db_path: data/setu.db
""".strip()
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "inherited-corporate-key")
    monkeypatch.setattr(config_module, "PROJECT_ROOT", Path(project_root))
    load_config.cache_clear()
    try:
        cfg = load_config(config_path)
    finally:
        load_config.cache_clear()

    assert cfg.anthropic_api_key is not None
    assert cfg.anthropic_api_key.get_secret_value() == "personal-project-key"
    assert "personal-project-key" not in repr(cfg)
