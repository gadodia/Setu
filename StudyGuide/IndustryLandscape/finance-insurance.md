# Agentic AI in Financial Services & Insurance (2024–2026)

> **Why this is the most relevant cluster for Setu:** same domain, same tensions — current external
> data, exact arithmetic, provenance, and "who's liable when the number is wrong." Read this one
> against `SUBMISSION_checkpoint2.md`; nearly every pattern here is one Setu already uses.

## Executive summary
Agentic AI is moving from pilot to early production across financial services, concentrated in
high-value, document-heavy work: insurance claims, lending underwriting, fraud detection, compliance,
wealth management, and **agentic commerce** (AI agents making purchases/payments). Unlike chatbots,
these systems execute multi-step workflows, call APIs, and decide with human-in-the-loop oversight.

- **Architecture:** ReAct, tool calling with MCP, RAG over structured docs, routing
  (deterministic→agentic fallback), reflection (generator-critic), multi-agent orchestration.
- **Bellwethers:** EY (audit, 130K professionals), Amex GBT + Claude (corporate travel), Robinhood
  (AI agent trading), Klarna/Stripe/PayPal (agentic commerce), Scaleport (insurance claims), Aviva
  (£230M fraud stopped).
- **Adoption:** pilot → early production (2024–2026); widespread expected ~2028.
- **India:** UPI + Account Aggregator + insurance-penetration gap (3.8% of GDP vs ~7% global) =
  greenfield for agentic underwriting, claims, and fraud.

## 1. Retail & investment banking
**Problems solved:** document-heavy ops (loan origination, KYC/AML, regulatory reporting), customer-
service overload (L1/L2 with escalation), fraud-detection latency, multi-jurisdiction compliance,
personalized wealth advice.
**Patterns:** ReAct; tool calling into KYC/transaction DBs, credit bureaus, market data; RAG over
policy/regulation; routing (high-confidence→fast path, ambiguous→agentic); supervisor over
fraud/compliance/service agents; HITL gating for large loans / suspicious transactions.
**Deployments:** Amex GBT + Anthropic Claude (policy-compliant travel booking, 2026); ING; Lloyds
(£2B cost-savings target); U.S. Bank (disciplined use-case framework); Fifth Third (post-merger
integration); JPMorgan ($18B/yr tech, ML CoE); HSBC (AWS cloud-first); Plaid + Fin (embedded
Link in-conversation).
**Bottlenecks:** liability for agent errors, explainability for regulators, legacy-core data silos,
customer trust, inference cost, <100ms fraud latency vs multi-step loop.
**India:** digital-first lending (60%+), UPI fraud surface (14B txns/mo), vernacular support gap,
190M credit-invisibles (alt-data underwriting via AA), RBI has no agentic guidance yet.

## 2. Wealth & portfolio management  *(Setu's exact domain)*
**Problems solved:** advisor capacity (50–100 clients each), research overload, personalization for
the mass-affluent, 24/7 monitoring, tax optimization.
**Patterns:** ReAct + tool use (reason about risk → market-data API → holdings → compute rebalance →
execute); multi-agent (research/trading/compliance/reporting); long-term user-profile memory + short-
term conversation; **HITL approval before trades** (regulatory); hard guardrails on position size,
concentration, leverage.
**Deployments:** Robinhood AI agent trading (2026); Morgan Stanley + OpenAI advisor copilot;
EY AI simulation for wealth; LlamaIndex due-diligence & deal-sourcing agents (SEC filings with
page-level citations).
**Bottlenecks:** fiduciary liability, suitability/audit logging, market-impact if millions of agents
act at once, hallucination on a misread earnings report, fragmented brokerage APIs.
**India:** mass-market robo-advice for the ₹5–25L segment, vernacular agents for Tier-2/3, gold
digitization, LTCG/STCG auto-computation, distributor disintermediation risk.

> **Direct Setu parallel:** "no LLM computes a financial figure," provenance to source, HITL before
> action, guardrails on concentration — Setu independently arrives at the same design the wealth
> incumbents are converging on.

## 3. Fintech & payments — agentic commerce
**Problems solved:** checkout friction (8–12 steps → "I want X"), payment orchestration (multi-rail
routing for cost/success), real-time fraud, cross-border FX/compliance, dispute auto-resolution.
**Patterns / protocols:** **A2A** (agent-to-agent), **AP2** (Agent Payments Protocol — cryptographically
signed cart/payment mandates on MCP+A2A), **MCP**, Verifiable Digital Credentials (non-repudiable
intent), routing+reflection, multi-agent (merchant↔payment↔issuer).
**Deployments:** Stripe Agentic Commerce Suite + OpenAI Agentic Commerce Protocol (ChatGPT checkout);
Stripe+AWS AgentCore; Natural ($30M, "payments for AI agents"); PayPal + Google conversational
commerce (A2A+AP2); Klarna Agentic Product Protocol (100M+ products) & ChatGPT shopping; Mastercard
agentic-commerce pipeline; Ramp ($750M @ $44B); SAP Concur + Gemini (expense automation via ReAct).
**Bottlenecks:** protocol interoperability, trust in agent purchases, prompt-injection fraud vectors,
regulatory ambiguity on agent-initiated payments, per-transaction inference cost, 5–10s agentic
checkout latency.
**India:** voice-based agentic UPI for low-literacy users, AA + agents for budgeting, BNPL surfacing,
cheapest-corridor remittances ($125B/yr inflows), 10M+ merchants <1% AI.

## 4. Lending & credit underwriting
**Problems solved:** manual underwriting, credit-invisibles (alt-data), fake-document fraud,
RBI/state compliance, post-disbursal monitoring.
**Patterns:** RAG over statements/returns; tool calls to CIBIL/GST/EPFO/UPI (via AA); ReAct
("DTI too high → request co-borrower → recompute"); reflection against policy limits; HITL for
>₹10L; hard caps on LTV/DTI/rate.
**Deployments:** Pacific Community Ventures ("AI for fair lending", Claude); LlamaIndex financial-doc
pipeline; U.S. Bank / Fifth Third (implied); Indian fintechs piloting micro-loan underwriting on AA.
**Bottlenecks:** RBI model-validation/audit-trail demands, bias/fairness, incomplete AA coverage,
misread-statement → NPA risk, inference cost, legacy LMS integration.
**India:** underused AA (50M of 600M+), MSME lending (63M, only 16% formal credit), agri loans via
satellite/weather/mandi data, vernacular voice, co-lending orchestration.

## 5. Fraud detection & AML/compliance
**Problems solved:** false positives (traditional rules flag 95%+ legit), <100ms real-time
decisioning, adaptive attacks, SAR overload, multi-jurisdiction sanctions.
**Patterns:** ReAct (observe txn → history → device → merchant risk → approve/decline/step-up); tool
calls to graph DBs / fraud APIs / sanctions lists; multi-agent (payment/identity/AML/insider);
reflection; behavior-baseline memory; HITL for >$10K.
**Deployments:** Visa + NVIDIA; Capital One (gen+agentic); Aviva (£230M fraud stopped, 2026); Lloyds;
Mastercard agentic-commerce fraud core.
**Bottlenecks:** <100ms latency vs multi-step reasoning, reason-code explainability, adversarial
probing, per-txn inference cost, novel-vector false negatives, DPDP/GDPR data-access limits.
**India:** UPI vishing/mule/SIM-swap detection, "digital arrest" scam signals, Aadhaar-eKYC synthetic-
identity cross-checks, trade-based ML on remittances, auto-drafted STR/CTR.

## 6. Insurance (underwriting, claims, fraud)
**Problems solved:** underwriting speed (days→minutes), claims backlog (triage + auto-approve low-
risk), 10–15% fraudulent claims, policy-query service, unstructured-doc extraction.
**Patterns:** RAG over policy/medical docs; tool calls to ICD/fraud/telematics/satellite; ReAct
(claim → policy → exclusions → request docs → compute payout); reflection vs limits; multi-agent;
HITL for >$50K.
**Deployments:** **Scaleport AI claims agent** (LlamaParse+LlamaIndex; 20–40min → ~10min, throughput
2×); Aviva fraud; Sutherland P&C agentic; LlamaIndex Agentic Document Workflows.
**Bottlenecks:** rare-condition complexity, regulator explainability, bias, fragmented medical records
(FHIR), fraud evasion, per-claim inference cost.
**India:** 80% health-uninsured, cashless real-time pre-auth, PMFBY crop payouts via satellite/IoT,
motor telematics (40% uninsured), microinsurance at scale, vernacular claims.

## Cross-cutting
**Common patterns:** ReAct · tool calling · RAG · routing · reflection/generator-critic · multi-agent
· HITL gating · guardrails · long+short-term memory · MCP/A2A/AP2 protocols.
**Stack:** OpenAI/Anthropic/Google/Llama · LlamaIndex/LangChain/ADK/Anthropic SDK · CrewAI/AutoGen ·
LlamaParse/Unstructured · Pinecone/Weaviate/Chroma · AWS Bedrock/Vertex/Azure/NVIDIA.
**Trajectory:** 2024 foundational (MCP, Agentic Commerce Protocol) → 2025 first production (Klarna,
Scaleport, Stripe) → 2026 scaling (Robinhood, EY, SAP Concur) → 2027–28 widespread (Gartner: "AI
agents outnumber sellers 10:1 by 2028").
**Common bottlenecks:** hallucination, regulation/liability, explainability, data silos, trust, cost,
latency, adversarial attacks.
**Why India is prime:** DPI (UPI/Aadhaar/AA/DigiLocker) + penetration gaps + cost sensitivity (<₹1/txn)
+ vernacular demand + a cautious-but-not-hostile RBI sandbox. Barriers: regulatory clarity, data
localization, vernacular NLP quality, digital literacy, trust deficit from past scams.
