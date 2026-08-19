# Setu: Retrieval Design Decision

**CMU Agentic AI Capstone — Checkpoint 3.1: Retrieval and External Knowledge**

## Do I need retrieval? Yes — but only in a few places, and never for numbers

Setu is a cross-border wealth agent. It pulls one person's US and Indian holdings into a single
currency-normalized view and answers: *what am I worth, how is it split up, and does that match my
risk target?* The real question this module raises isn't "RAG or no RAG." It's **where retrieval
belongs and where it doesn't.** My answer: use retrieval for the fuzzy, knowledge-heavy parts, and
keep it away from the numbers.

Here's why. Net worth, allocation, and currency exposure are exact math over structured rows in a
SQLite ledger, using a real FX rate. A similarity search would actually be worse here: it returns
what *looks* close when I need exactly the right rows. Asking a vector store for "the holdings that
seem to belong to this account" is a bug waiting to happen — `WHERE account_id = ?` is the right
tool. So the ledger is not something I retrieve over. The rule I follow: **numbers and facts →
SQLite; fuzzy matching and reference knowledge → vectors.**

Three jobs, though, really do need retrieval, and neither a prompt nor a SQL query handles them well:

1. **How to value an insurance policy.** An Indian policy (term / endowment / ULIP) is valued by
   rules that depend on its type — a ULIP's value is `units × current NAV`, while a pure term plan
   has no asset value at all, just a death benefit. These rules are a small, curated set that I'd
   rather look up than trust the model to remember.
2. **User corrections.** When someone fixes a mislabeled holding, that fix should come back the next
   time a similar statement shows up — a fuzzy match on the text, not an exact key.
3. **Past runs.** "Last time a Tata statement looked like this, the premium was here."

## How I'd wire it up

Setu gets a **vector store on the side** (`sqlite-vec`, sitting next to the ledger; Chroma as a
backup), filled by a **local embedding model** (`nomic-embed-text` through Ollama). Running the
embedder locally isn't optional — statement text has personal data in it, and Setu's whole promise is
that raw statements never leave the machine. Same rule that covers the extraction model covers this.

The first thing I'd embed is the **policy-valuation knowledge base** (`knowledge/policy_rules.yaml`)
— a short, hand-written, versioned file of the term/endowment/ULIP rules and where each came from.
Before valuing a policy, the agent embeds the policy description, pulls the closest matching rule,
and drops it into the model's context. The file lives outside the model and I can edit it directly,
so fixing a rule is a one-line change, not a retraining job.

## An example where retrieval changes the answer

Say a statement reads *"Tata AIA Fortune Pro — Fund Value ₹4,80,000; Sum Assured ₹50,00,000."* A
prompt-only agent asked for net worth tends to grab the bigger, flashier number — booking
₹50,00,000 (the *insurance coverage*) as an asset and overstating net worth by about 10×.

With retrieval, the agent embeds that line, pulls back the **ULIP** rule — *"unit-linked → asset
value = fund value; sum assured is coverage, not an asset"* — and books **₹4,80,000** as the asset
while recording the ₹50,00,000 as protection. The retrieved rule is the only thing that tells "fund
value" apart from "sum assured"; without it the model can't see the difference. That's retrieval
changing the actual number the user sees. And it still runs through the existing guardrail: a Python
tool does the math, the model never computes the figure itself.

## Key retrieval choices

- **Source:** a curated, dated policy-rules file (small and trustworthy) plus a growing store of
  user corrections and past runs.
- **Chunking:** **one rule per record** — not fixed-size text windows. A rule is the natural unit;
  splitting one in half would cut the condition off from its result. Corrections are stored one per
  record as `(statement snippet + holding description) → correction`.
- **How many results:** **top 3**, with a minimum similarity score. I keep the number low because
  the file is high-quality and a confident wrong rule is worse than none. The score cutoff also lets
  retrieval come back empty and ask the user instead of forcing a bad match.

## One failure mode, and how I handle it

The main risk is a **wrong-but-confident match** — say an endowment policy lands close to the ULIP
rule and pulls back the wrong valuation, giving a number that looks fine but isn't. Three things
keep that in check. **One,** the similarity cutoff: below it, retrieval returns nothing and the
agent asks the user rather than acting on a weak guess — it's allowed to say "I don't know."
**Two,** the number stays deterministic: retrieval only hands over the *rule*; a Python tool applies
it, and the existing **reconciliation** step compares the total against the statement's stated
balance, so a bad rule that throws off the total gets caught before anyone sees it. **Three,** every
rule keeps its source, so each valuation is traceable and a bad rule is easy to fix. Retrieval makes
the answers better grounded; it never becomes a new way to sneak in a made-up number.

*Note on progress: the deterministic core, the ingestion loop, and reconciliation (Weeks 1–3) are
built and tested. The vector store and policy-rules file described here are the Week 5 build, per
the project plan.*
