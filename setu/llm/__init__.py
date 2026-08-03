"""LLM client layer — the probabilistic side of Setu.

The router picks local (Ollama) vs cloud (Claude) per stage from config. Local handles PII-heavy
extraction so raw statement text never leaves the machine; Claude drives reasoning + tool-calling.
No client here ever computes a financial figure — that stays in `tools/` (ARCHITECTURE.md §1).
"""
