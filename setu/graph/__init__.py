"""LangGraph runtime for Setu — the state machine that executes the ReAct ingestion loop.

`state.py`  — the shared State (working memory), a TypedDict every node reads/writes.
`nodes.py`  — node functions wrapping agents/tools; each takes State, returns a partial update.
`build.py`  — assembles the graph, wires the self-correcting conditional edge, and compiles it
              with the SQLite checkpointer + a human-in-the-loop interrupt.
"""
