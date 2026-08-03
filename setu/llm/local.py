"""Local model client (Ollama) — for PII-heavy structured extraction.

Uses Ollama's structured-output support (JSON schema-constrained decoding) so the model returns
valid JSON matching a pydantic schema. Runs fully offline; raw statement text stays local.
"""

from __future__ import annotations

import json
from typing import TypeVar

from ollama import Client
from pydantic import BaseModel

from setu.config import Config, load_config

T = TypeVar("T", bound=BaseModel)


class LocalModelError(RuntimeError):
    pass


class LocalClient:
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.model = self.config.model_router.extraction.model
        self._client = Client(host=self.config.ollama.host)

    def extract_structured(
        self,
        prompt: str,
        schema: type[T],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """Prompt the local model and parse its JSON response into `schema`.

        Uses `format=<json schema>` so decoding is constrained to valid JSON. temperature=0
        for deterministic, reproducible extraction.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = self._client.chat(
                model=self.model,
                messages=messages,
                format=schema.model_json_schema(),
                options={"temperature": temperature},
            )
        except Exception as e:  # ollama connection / model errors
            raise LocalModelError(
                f"Ollama call failed (model={self.model}, host={self.config.ollama.host}): {e}"
            ) from e

        content = resp["message"]["content"]
        try:
            return schema.model_validate_json(content)
        except Exception as e:
            raise LocalModelError(
                f"Local model returned invalid JSON for {schema.__name__}: {e}\nGot: {content[:500]}"
            ) from e

    def available(self) -> bool:
        """True if Ollama is reachable and the configured model is present."""
        try:
            models = self._client.list().get("models", [])
            names = {m.get("model", m.get("name", "")) for m in models}
            return any(self.model in n for n in names)
        except Exception:
            return False
