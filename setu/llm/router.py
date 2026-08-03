"""Model router — picks the client for a stage from config (ARCHITECTURE.md §1).

Keeps the "synthetic now, real later / local vs cloud" switch a config value, not a code change.
"""

from __future__ import annotations

from setu.config import Config, load_config
from setu.llm.claude import ClaudeClient
from setu.llm.local import LocalClient


class Router:
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()

    def for_stage(self, stage: str):
        """Return the client configured for a stage ('extraction'|'classification'|'reasoning')."""
        cfg = getattr(self.config.model_router, stage)
        if cfg.provider == "local":
            return LocalClient(self.config)
        if cfg.provider == "claude":
            return ClaudeClient(self.config)
        raise ValueError(f"Unknown provider {cfg.provider!r} for stage {stage!r}")

    def extraction_client(self) -> LocalClient | ClaudeClient:
        return self.for_stage("extraction")

    def reasoning_client(self) -> ClaudeClient:
        return self.for_stage("reasoning")
