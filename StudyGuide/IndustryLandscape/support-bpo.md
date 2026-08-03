# Agentic AI in Customer Support, Contact Centers & BPO/ITES/GCC (2024–2026)

> **Why it matters:** the clearest ROI numbers in the landscape *and* the most India-exposed
> white-collar workforce (5M+ in BPO/ITES/GCC). Also the sector with the cleanest examples of
> outcome-based pricing and human-in-the-loop escalation UX.

## 1. Customer support automation  *(most mature agentic area)*
**Problems solved:** Tier-1 deflection (refunds, order status, account updates), 24/7 multilingual
coverage, resolution speed (11min → <2min at Klarna), knowledge retrieval, escalation-with-context.
**Patterns:**
- **Reasoning engines:** Salesforce Agentforce **Atlas** (decompose→evaluate→plan); Intercom Fin
  **Apex** models (65% hallucination reduction vs baseline); Decagon **Agent Operating Procedures**
  (NL workflow definitions, testable without eng sprints).
- **Tool/API calling:** update accounts, process refunds, cancel orders (REST/MuleSoft/MCP).
- **RAG/memory:** grounding from help centers/SOPs/tickets; **Sierra Horizon** long-horizon memory
  for proactive engagement; Amazon Connect "shared intelligence that gets smarter over time."
- **Multi-agent:** Forethought (Discover/Solve/Triage/QA/Assist); Ada (multi-LLM orchestration).
- **HITL escalation** with full-context transfer; **guardrails** (SOC2/ISO/GDPR/HIPAA/PCI).

**Deployments (vendor-reported metrics):**
| Platform | Customer | Metric |
|---|---|---|
| Klarna (OpenAI) | internal | 2.3M convos/mo, 66% deflection, $40M profit impact |
| Intercom Fin | 12K+ customers (Anthropic, Clay) | 76% avg resolution, 2M weekly |
| Decagon | Chime / Duolingo / ClassPass | 70% / 80% / 95% cost reduction |
| Zendesk AI | Babbel / TeamSystem | +50% resolution / 80% automation |
| Forethought | Upwork | 50% faster resolution, 65% self-serve |
| Ada | IPSY | $2.7M savings, 943% ROI in 4 months |
| Cresta | Snap Finance / Cox | 5.5× containment / +20% revenue |
| Salesforce Agentforce | 18K+ companies | OpenTable, SharkNinja, Indeed, Heathrow |
| Sierra | Rocket, SiriusXM, Sonos, SoFi | outcome-based pricing |

Funding: Sierra ($175M, $100M ARR <2yrs), Wonderful ($150M @ $2B), Parloa ($350M @ $3B); Zendesk
acquired Ultimate.ai.
**Adoption:** early production → widespread; leaders report 65–85% deflection.
**Bottlenecks:** 15–40% still escalate; hallucination/brand risk in regulated industries;
escalation tone/empathy gaps; legacy integration; consumer resistance ("I want a real person");
CSAT on-par not superior; unclear long-term LTV impact.
**India:** ~1.5M support-BPO workers directly exposed; multilingual (Fin 35+, Zendesk 80 langs) favors
diversity; Yellow.ai/Kore.ai positioned but limited public traction; gaps in vernacular/regional
languages, cultural context, India-accent voice; TCS/Infosys/Wipro packaged offerings not publicly
visible (many 404s → stealth/consulting/internal).

## 2. Contact center operations
**Snapshot:** ~$400B+ market; India ~40% of offshore ops. Focus split between **agent assist**
(augmentation) and autonomous resolution.
**Problems solved:** agent productivity (real-time guidance), QA (100% scoring vs 1–5% sampling),
forecasting/routing, training ramp (months→weeks), compliance monitoring.
**Patterns:** real-time agent assist (Cresta, Amazon Connect AI teammates, Forethought Copilot);
conversation intelligence (100% analysis, sentiment, escalation prediction); triage/routing;
supervisor escalation with context; compliance guardrails.
**Deployments:** Cresta (United/Alaska Airlines, Marriott/Hilton, Cox +20% revenue, Brinks +30pt NPS);
Amazon Connect (Cochlear 22× QA scale, TUI, American Airlines); Five9; Agentforce Contact Centre;
Zendesk; Genesys; NICE Enlighten.
**Adoption:** pilot→early production; **agent assist more adopted than autonomous voice**; traditional
India BPOs (Concentrix/Teleperformance/TTEC) adoption unclear (no public case studies).
**Bottlenecks:** voice complexity (accent/noise/latency <1s), agent change-management/union concerns,
legacy PBX/IVR integration, 12–24mo ROI, recording-consent/data-residency.
**India:** ~2M contact-center workers, two-tier disruption (Tier-1 high exposure, Tier-2/3 augmented);
agent-assist preserves jobs (more palatable); India-accent voice underrepresented in training data
(an opportunity); no large reskilling programs announced.

## 3. BPO/ITES & Global Capability Centers (GCC)
**Snapshot:** **the most agentic-AI-exposed white-collar industry globally** — 5M+ workers; 1,500+
GCCs (1.5M workers). Yet public adoption data is scarce (workforce sensitivity + client confidentiality).
**Problems solved:** back-office (invoices, claims, reconciliation), IT helpdesk, HR ops,
finance/accounting, multi-step complaint resolution.
**Patterns:** process reasoning engines (Automation Anywhere APAS + Mozart Orchestrator); RPA+agentic
hybrid (LLM reasoning over unstructured data on top of RPA); multi-step workflows; audit-trail/privacy
governance.
**Deployments:** Automation Anywhere (complaint resolution AHT reduction); UiPath (status unclear).
Indian IT-services (TCS/Infosys/Wipro/HCL/Tech Mahindra): **multiple 404s on product pages** → likely
stealth/pilot, services-not-product positioning, or internal-first due to workforce sensitivity. No
named GCC production deployments found.
**Adoption:** pilot, limited production. Indian BPOs not publicly showcasing (announcing automation =
negative PR; contracts restrict disclosure).
**Bottlenecks:** legacy integration (SAP/Oracle/mainframe), near-100% accuracy for financial txns,
workforce-transition politics, client-adoption caution, trust/brand risk.
**India — the core tension:** 5M workers in 50–80% automatable roles; **no large-scale reskilling
announced**; Klarna's "700 agents" extrapolates to millions of exposed jobs *if* global clients adopt
at scale — but **no major layoffs yet** (gradual attrition, not mass displacement). Opportunities:
hybrid augmentation (cost-competitive + preserves jobs), India-built platforms (Yellow.ai/Kore.ai),
continued GCC growth into higher-value work, reskilling-at-scale as a policy opportunity. Gaps:
vernacular/regional-language AI, India-optimized platforms, regulatory framework, transparency.
Policy: export competitiveness ($150B+), domestic-CX opportunity, weak safety net, state-level
employment pressure (Karnataka/Telangana/Tamil Nadu).

## Cross-cutting
**Maturity by channel:** text (mature, 65–85% resolution) > voice (early, accent/emotion developing)
> omnichannel (context persistence emerging) > proactive (Sierra Horizon, novel).
**Business-model evolution:** **outcome-based pricing** (Sierra "pay for value delivered"),
resolution-based tiers (Zendesk), hybrid human+AI (agent assist more palatable than full automation).
**Vendor landscape:** US platforms dominate (Sierra, Salesforce, Zendesk, Intercom, Decagon, Amazon
Connect, Cresta); Indian platforms (Yellow.ai, Kore.ai) emerging but low traction; IT-services product
offerings not visible.
**Research caveat:** metrics are vendor-reported, not audited; India data limited by access restrictions
and BPO opacity.
