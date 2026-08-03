# Week 2 — Tool / Function Calling (the determinism spine)

**Build this week:** the deterministic tools — `pdf_extract.py`, `fx.py`, `calc.py` — plus the two
ways an LLM reaches them: the **local structured-output extractor** (`extraction.py` over Ollama) and
the **Claude tool-calling loop** (`llm/claude.py` + `tools/registry.py`), wired into `setu ingest`
and `setu ask`.
**Study goal:** understand *how an LLM calls code* — what a "tool" actually is over the wire, how the
agentic loop runs, and the judgment call at Setu's heart: **when to let the model decide vs. when to
make deterministic Python compute.**

> **Aligned to CMU Module 2** ("Tool / Function Calling"). Outcomes: (1) how tool use works
> *internally* — the model emits a structured call, your code runs it, the result is fed back; (2)
> **JSON-schema tools** and **constrained/structured output**; (3) the **agentic loop** (call →
> execute → observe → repeat); (4) the design rule for **deterministic code vs. the LLM**. Grounded in
> Setu.

---

## 1. Why tool calling exists

A bare LLM (Week 1) is a text predictor: it has no clock, no calculator, no file system, and its
"knowledge" is frozen at training time. Ask it "what's my net worth in USD?" and it will *pattern-match
a plausible-looking number* — confidently wrong, and untraceable. That failure mode is fatal for a
wealth agent where every figure must be exact and provenance-backed.

**Tool calling** is the bridge. It lets the model do the one thing it is genuinely good at —
**deciding, in context, what needs to happen** — while delegating the actual *doing* (arithmetic,
FX conversion, PDF parsing, DB queries) to ordinary deterministic code. The model proposes; the code
disposes. This is the mechanism that operationalizes Setu's spine:

> **The LLM decides / classifies / explains. Deterministic Python tools compute. No LLM ever computes
> a financial figure.**

---

## 2. What a "tool" actually is (over the wire)

A tool is nothing magic — it's a **JSON-schema description of a function** you hand the model, plus the
real function on your side. Setu's registry (`tools/registry.py`) declares them exactly this way:

```json
{
  "name": "fx_convert",
  "description": "Convert an amount from a currency into the base currency (USD).",
  "input_schema": {
    "type": "object",
    "properties": {
      "amount":   {"type": "number"},
      "currency": {"type": "string", "description": "ISO code, e.g. INR"}
    },
    "required": ["amount", "currency"]
  }
}
```

The loop, step by step:

1. You send the user's message **+ the list of tool schemas** to the model.
2. The model, instead of answering, may emit a **structured `tool_use` block**: `{name:"fx_convert",
   input:{amount:320000, currency:"INR"}}`. It does **not** run anything — it just names the function
   and fills the arguments (the schema constrains it to valid shapes).
3. **Your code** (`build_executor`'s `dispatch`) runs the *real* `fx.convert(...)` and gets
   `Decimal("3849.60")`.
4. You feed that result back as a **`tool_result`** message.
5. The model reads the observation and either calls another tool or writes the final answer.

The key mental model: **the model emits *intent*, your runtime supplies *fact*.** The number
`3849.60` was computed by Python, never by the LLM — the LLM only decided *that* a conversion was
needed and *which* currency.

---

## 3. Two flavors of "model calls code" in Setu

Setu uses tool calling in **two distinct modes**, and knowing why there are two is the crux of Week 2.

### (a) Agentic tool-calling loop — Claude, for reasoning (`llm/claude.py`)

Used by `setu ask`. Claude is given the tool schemas and **autonomously decides** which to call, in
what order, looping until it can answer. This is the multi-round `run_tool_loop`:

```
user: "How much of my wealth is in USD vs INR?"
 └─ Claude → tool_use: compute_net_worth {}
     └─ dispatch → {net_worth:"262413.30", by_currency:{USD:"224…", INR:"37…"}}
 └─ Claude reads it → writes the answer (no further tool needed)
```

Claude picks the tool; the loop keeps going while `stop_reason == "tool_use"` and stops on
`end_turn`. This is **open-ended** — good when you don't know in advance which/how many calls a
question needs.

### (b) Constrained structured output — the local model, for extraction (`extraction.py`)

Used by `setu ingest`. Here we *don't* want the model to freely choose — we want it to fill **one
fixed schema** (`ExtractionResult` → a list of `ExtractedHolding`). Ollama's `format=<JSON schema>`
does **constrained decoding**: the model is *forced* to emit tokens that satisfy the schema, so the
output always parses. It's tool calling collapsed to a single guaranteed-shape call.

```python
client.extract_structured(prompt, ExtractionResult, system=_SYSTEM)  # returns a validated pydantic obj
```

**Why the local model here?** This is the PII-heavy step — raw statement text with account numbers,
names, balances. Running extraction on **Ollama (local)** means that raw text **never leaves the
machine**; only the cleaned, structured holdings (and only when needed) go to a cloud model. Cloud
Claude does the reasoning where there's no raw PII. That's the **hybrid model strategy**, and it's a
privacy decision expressed as a routing decision (`llm/router.py` picks provider per stage from
`config.yaml`).

| | (a) Agentic loop (Claude) | (b) Structured output (Ollama) |
|---|---|---|
| Who chooses the tool | the model, autonomously | you (one fixed schema) |
| Rounds | many, until `end_turn` | exactly one |
| Used for | `setu ask` — open reasoning | `setu ingest` — extraction |
| Runs where | cloud (no raw PII) | local (PII stays home) |
| Guarantee | flexible | output always matches schema |

---

## 4. The design rule: deterministic code vs. the LLM

The whole architecture turns on **drawing this line in the right place**. The test:

> **Is there exactly one correct answer computable from the data?** → deterministic Python.
> **Does it need judgment, classification, or natural language?** → the LLM.

| Job | Who does it | Why |
|---|---|---|
| Sum holdings, convert FX, compute allocation % | **`calc.py` / `fx.py`** (Python, `Decimal`) | one right answer; must be exact, testable, provenance-backed |
| Pull text + tables out of a PDF | **`pdf_extract.py`** (pdfplumber) | mechanical; no judgment needed |
| "Is this row EQUITY or DEBT? US or India?" | **LLM** (extraction) | classification from messy, varied text |
| "Which tool answers this question?" | **LLM** (Claude loop) | planning in context |
| "Explain why I'm over my USD target" | **LLM** (insights, later) | natural-language synthesis over computed facts |

Two anti-patterns Week 2 is built to avoid:

- **LLM-as-calculator** — asking the model to add or convert. Non-deterministic, unauditable, wrong.
  Every figure in Setu is a `Decimal` from `calc.py`; the tests assert exact values
  (`Decimal("262413.3000000")`).
- **Regex-as-classifier** — hand-writing parsers for every statement format. Brittle; breaks on the
  next bank's layout. The LLM *classifies*; deterministic code *computes* — each does what it's good
  at.

`money` is `Decimal` everywhere (never `float`) precisely because this is financial truth — `float`
rounding errors are unacceptable in a ledger.

---

## 5. Connection to what we build in Week 2

- **`pdf_extract.py`** — deterministic PDF → `ExtractedDoc(pages, tables, full_text)`. No
  interpretation; just faithful extraction. Tested against the synthetic statements (brokerage text +
  tables recovered, CAS has a NAV column).
- **`fx.py` / `calc.py`** — the compute core. `convert()` and `compute_net_worth()` aggregate to base
  currency by asset class / geography / currency. These are the "tools" the model calls but never
  reimplements.
- **`tools/registry.py`** — the JSON-schema declarations (`TOOL_SCHEMAS`) + `build_executor` dispatch
  that runs the real functions and returns JSON-serializable results (Decimals as strings, so no
  float ever sneaks in).
- **`llm/local.py` + `extraction.py`** — constrained structured output on Ollama; the private
  extraction path.
- **`llm/claude.py` + `llm/router.py`** — the agentic loop and the provider router that sends each
  stage to the right model per `config.yaml`.
- **`setu ingest` / `setu ask`** — the two modes made real on the CLI, with `--trace` exposing the
  Thought/Action/Observation of the loop (a preview of Week 3's ReAct).

> **The Week 2 punchline:** a tool is a JSON-schema function the model can *call but not execute* — it
> emits the intent, your deterministic code supplies the fact. Setu uses the **autonomous loop** for
> open reasoning (Claude) and **constrained structured output** for private extraction (Ollama), and
> holds one hard line throughout: **the LLM decides, Python computes, and no number is ever the
> model's invention.**

---

## 6. Further reading (optional)
- Anthropic docs — *Tool use (function calling)* and the messages/tool_result loop.
- Ollama docs — *Structured outputs* (`format` as a JSON schema; constrained decoding).
- Schick et al., 2023 — *Toolformer: Language Models Can Teach Themselves to Use Tools*.
- Course Module 2 materials on tool/function calling and structured output.

See `cheatsheet.md` for the one-page recall version.
