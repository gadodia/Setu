"""Load and expose Setu configuration.

Reads ``config.yaml`` (deterministic settings) and ``.env`` (secrets). Exposes a typed
``Config`` object so the rest of the code never touches raw dicts or ``os.environ`` directly.
FX rates are parsed to ``Decimal`` here so no float ever enters a money computation.
"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Project root = the directory containing config.yaml (one level above this file's package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class Paths(BaseModel):
    data_dir: Path
    synthetic_dir: Path
    inbox_dir: Path
    db_path: Path


class Thresholds(BaseModel):
    reconcile_tolerance: Decimal = Decimal("0.005")


class ModelStage(BaseModel):
    """One routed stage: which provider and which concrete model."""

    provider: str = "claude"       # "local" (Ollama) or "claude"
    model: str = "claude-sonnet-5"


class ModelRouter(BaseModel):
    extraction: ModelStage = Field(
        default_factory=lambda: ModelStage(provider="local", model="qwen2.5:7b")
    )
    classification: ModelStage = Field(default_factory=ModelStage)
    reasoning: ModelStage = Field(default_factory=ModelStage)


class Ollama(BaseModel):
    host: str = "http://localhost:11434"


class Config(BaseModel):
    base_currency: str = "USD"
    paths: Paths
    thresholds: Thresholds = Field(default_factory=Thresholds)
    fx_rates: dict[str, Decimal] = Field(default_factory=dict)
    model_router: ModelRouter = Field(default_factory=ModelRouter)
    ollama: Ollama = Field(default_factory=Ollama)

    # Secrets loaded from .env (never from config.yaml).
    anthropic_api_key: str | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.paths.db_path}"

    def resolve_paths(self) -> None:
        """Make relative paths absolute against the project root and ensure dirs exist."""
        for name in ("data_dir", "synthetic_dir", "inbox_dir", "db_path"):
            p = getattr(self.paths, name)
            if not p.is_absolute():
                setattr(self.paths, name, PROJECT_ROOT / p)
        # Create directories (db_path's parent, not the file itself).
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.synthetic_dir.mkdir(parents=True, exist_ok=True)
        self.paths.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.paths.db_path.parent.mkdir(parents=True, exist_ok=True)


def _coerce_decimals(raw: dict) -> dict:
    """Convert fx_rates and tolerance values to Decimal via str (never via float)."""
    if "fx_rates" in raw and raw["fx_rates"]:
        raw["fx_rates"] = {k: Decimal(str(v)) for k, v in raw["fx_rates"].items()}
    if "thresholds" in raw and raw["thresholds"]:
        thr = raw["thresholds"]
        if "reconcile_tolerance" in thr:
            thr["reconcile_tolerance"] = Decimal(str(thr["reconcile_tolerance"]))
    return raw


@lru_cache(maxsize=1)
def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load config.yaml + .env into a typed Config (cached; call load_config.cache_clear() to reload)."""
    load_dotenv(PROJECT_ROOT / ".env")

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    raw = _coerce_decimals(raw)
    config = Config(**raw)
    config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    config.resolve_paths()
    return config
