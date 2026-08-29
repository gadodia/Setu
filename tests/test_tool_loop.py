"""Test the Claude tool-calling loop with a MOCKED Anthropic client (no key/network needed).

Proves the loop mechanics: a tool_use response triggers executor dispatch, the result is fed
back, and a final text response ends the loop with the answer + trace.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from setu.llm.claude import ClaudeClient


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, tool_input, id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id)


class _FakeMessages:
    """Scripts two rounds: first asks for a tool, then answers."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _text_block("I need the net worth."),
                    _tool_use_block("compute_net_worth", {}),
                ],
            )
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[_text_block("Your net worth is $262,413.30.")],
        )


@pytest.fixture
def claude_client(config, monkeypatch):
    # Bypass __init__ (which requires a key) and inject the fake transport.
    client = ClaudeClient.__new__(ClaudeClient)
    client.config = config
    client.model = "claude-sonnet-5"
    client._client = SimpleNamespace(messages=_FakeMessages())
    return client


def test_tool_loop_executes_tool_and_answers(claude_client):
    executed = {}

    def executor(name, tool_input):
        executed["name"] = name
        return {"net_worth": "262413.30", "base_currency": "USD"}

    result = claude_client.run_tool_loop(
        "What is my net worth?",
        tools=[{"name": "compute_net_worth", "description": "x",
                "input_schema": {"type": "object", "properties": {}}}],
        executor=executor,
    )

    assert executed["name"] == "compute_net_worth"
    assert "262,413.30" in result.answer
    assert result.rounds == 2

    kinds = [s.kind for s in result.trace]
    assert "tool_call" in kinds and "tool_result" in kinds


def test_tool_loop_records_executor_errors(claude_client):
    def failing_executor(name, tool_input):
        raise RuntimeError("boom")

    result = claude_client.run_tool_loop(
        "What is my net worth?",
        tools=[{"name": "compute_net_worth", "description": "x",
                "input_schema": {"type": "object", "properties": {}}}],
        executor=failing_executor,
    )
    # Loop still completes; the error is surfaced as a tool_result, not a crash.
    tool_results = [s for s in result.trace if s.kind == "tool_result"]
    assert tool_results and "boom" in str(tool_results[0].content)


def test_tool_loop_uses_configured_output_limit_and_reports_truncation(claude_client):
    recorded = {}

    class TruncatedMessages:
        def create(self, **kwargs):
            recorded.update(kwargs)
            return SimpleNamespace(
                stop_reason="max_tokens",
                content=[_text_block("### Answer\n\nA partial grounded answer")],
            )

    claude_client._client = SimpleNamespace(messages=TruncatedMessages())

    result = claude_client.run_tool_loop("Explain the portfolio", tools=[], executor=lambda *_: {})

    assert recorded["max_tokens"] == claude_client.config.claude.max_output_tokens
    assert result.truncated is True
    assert result.stop_reason == "max_tokens"
    assert result.answer.startswith("### Answer")
