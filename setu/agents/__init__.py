"""Specialized sub-agents coordinated by the Orchestrator (concept #5).

Each agent owns one narrow responsibility and is independently testable:
  IngestionAgent      — parse a statement, extract + classify holdings (local model)
  ReconciliationAgent — check the extracted sum against the statement's stated total (ToT hypotheses)

The Orchestrator (orchestrator.py) runs the compiled LangGraph, which dispatches these agents as
nodes, observes their results, and re-plans / interrupts on mismatch.
"""
