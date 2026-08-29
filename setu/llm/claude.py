"""Claude client + the tool-calling loop (graded concept #1).

The loop: send messages + tool schemas → Claude decides to call a tool → we execute the
deterministic Python tool → feed the JSON result back → repeat until Claude answers with no
further tool call. Claude decides *which* tool and *interprets* results; the tool computes.

Emits a structured trace of every thought/tool_call/tool_result so the loop is observable
(the basis for the Week 3 ReAct feed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from anthropic import Anthropic

from setu.config import Config, load_config


class ClaudeError(RuntimeError):
    pass


OFFICIAL_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def _personal_api_base_url(base_url: str) -> str:
    """Allow only Anthropic's official HTTPS origin for personal Setu credentials."""
    parsed = urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    safe = (
        parsed.scheme == "https"
        and parsed.hostname == "api.anthropic.com"
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and parsed.path.rstrip("/") == ""
        and not parsed.query
        and not parsed.fragment
    )
    if not safe:
        raise ClaudeError(
            "Setu's personal API key may only be sent to the official Anthropic API "
            f"({OFFICIAL_ANTHROPIC_BASE_URL})."
        )
    return OFFICIAL_ANTHROPIC_BASE_URL


@dataclass
class TraceStep:
    kind: str            # "text" | "tool_call" | "tool_result"
    content: Any
    tool_name: str | None = None


@dataclass
class LoopResult:
    answer: str
    trace: list[TraceStep] = field(default_factory=list)
    rounds: int = 0
    stop_reason: str | None = None
    truncated: bool = False
    max_output_tokens: int = 0


# A tool executor maps a tool name + input dict to a JSON-serializable result.
ToolExecutor = Callable[[str, dict], Any]


class ClaudeClient:
    def __init__(
        self,
        config: Config | None = None,
        *,
        base_url: str = OFFICIAL_ANTHROPIC_BASE_URL,
    ):
        self.config = config or load_config()
        if not self.config.anthropic_api_key:
            raise ClaudeError("ANTHROPIC_API_KEY not set (add it to .env).")
        self.model = self.config.model_router.reasoning.model
        self.base_url = _personal_api_base_url(base_url)
        self._client = Anthropic(
            api_key=self.config.anthropic_api_key.get_secret_value(),
            # Pass explicitly so an inherited corporate ANTHROPIC_BASE_URL cannot redirect
            # Setu's personal credential to another gateway.
            base_url=self.base_url,
        )

    def run_tool_loop(
        self,
        user_prompt: str,
        tools: list[dict],
        executor: ToolExecutor,
        system: str | None = None,
        max_rounds: int | None = None,
        max_output_tokens: int | None = None,
    ) -> LoopResult:
        """Run the agentic tool-calling loop until Claude produces a final text answer."""
        round_limit = (
            self.config.claude.max_tool_rounds if max_rounds is None else max_rounds
        )
        output_limit = (
            self.config.claude.max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )
        if round_limit < 1:
            raise ValueError("max_rounds must be at least 1")
        if output_limit < 1:
            raise ValueError("max_output_tokens must be at least 1")
        messages: list[dict] = [{"role": "user", "content": user_prompt}]
        result = LoopResult(answer="", max_output_tokens=output_limit)

        for round_i in range(1, round_limit + 1):
            result.rounds = round_i
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=output_limit,
                system=system or "",
                tools=tools,
                messages=messages,
            )

            # Record any assistant text.
            tool_uses = []
            for block in resp.content:
                if block.type == "text":
                    result.trace.append(TraceStep("text", block.text))
                elif block.type == "tool_use":
                    tool_uses.append(block)
                    result.trace.append(
                        TraceStep("tool_call", dict(block.input), tool_name=block.name)
                    )

            # No tool calls → Claude is done; collect final text.
            if resp.stop_reason != "tool_use":
                result.stop_reason = resp.stop_reason
                result.answer = "".join(
                    b.text for b in resp.content if b.type == "text"
                ).strip()
                result.truncated = resp.stop_reason == "max_tokens"
                return result

            # Append the assistant turn, then execute each requested tool.
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for tu in tool_uses:
                try:
                    output = executor(tu.name, dict(tu.input))
                    content = output if isinstance(output, str) else _json(output)
                    is_error = False
                except Exception as e:
                    content = f"Tool error: {e}"
                    is_error = True
                result.trace.append(
                    TraceStep("tool_result", content, tool_name=tu.name)
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": content,
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": tool_results})

        raise ClaudeError(f"Tool loop did not converge in {round_limit} rounds.")


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)
