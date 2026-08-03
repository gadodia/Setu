# Agentic AI in Software Engineering & IT Operations (2024–2026)

> **Why read this one for architecture:** the deepest technical patterns in the whole landscape
> originate here — ReAct, the **Agent-Computer Interface (ACI)** design discipline, sandboxed
> execution, and **MCP** itself. If you want to understand *how* Setu's tools should be shaped for an
> agent to use them well, this is the reference cluster.

## 1. AI coding agents / autonomous software development
**Snapshot:** the most mature agentic segment — 97%+ of enterprise devs have used AI coding tools,
62% daily (up from 44%). GitHub passed 150M developers. Productivity gains up to 55% (Copilot).
**India:** 5.4M+ developers (2nd largest pool). IT-services giants face a labor-arbitrage squeeze;
Devin partnered with **Cognizant and Infosys** — acceptance, not resistance.

**Problems solved:** boilerplate, codebase navigation at scale, bug reproduction/root-cause, legacy
modernization (COBOL→Java), test generation, context-switch reduction.

**Architecture patterns (the core reference):**
- **ReAct** — dominant. THOUGHT → ACTION → OBSERVATION until done (SWE-agent, Claude's 200+ turn runs).
- **Plan-then-execute** — Copilot Workspace: analyze issue → NL plan (human-editable) → execute → test.
  Committing to a strategy before touching code reduces hallucination.
- **Self-correction / reflection** — on a failed edit, receive the error and retry with corrected
  context; Devin's confidence scoring (🟢🟡🔴) is meta-cognition before spending resources.
- **Tool calling + ACI design** — Claude's SWE-bench agent used only three tools (Bash, str-replace
  Edit, Read). The **ACI insight** (SWE-agent paper, arXiv:2405.15793): tools designed for *agent
  ergonomics* — error-proofing (absolute paths, exact-match edits), actionable feedback on every call,
  documentation-as-affordance — outperform kitchen-sink APIs. *This is the design lens for Setu's tools.*
- **Execution sandboxing** — Devin runs each session in an isolated VM (blockdiff snapshots for rollback).
- **RAG/memory over codebases** — Aider's "repomap," Cursor semantic indexing, hierarchical
  summarization for million-line repos; LangGraph cross-session memory; Devin schedules recurring
  sessions maintaining state.
- **Multi-agent** — supervisor→workers (Devin delegates to a team of Devins in parallel VMs; Bedrock
  supervisor pattern), agent handoffs (OpenAI Swarm), hybrid routing (Devin Fusion, ~35% cheaper),
  parallel fleets (Cursor across repos).
- **HITL** — LangGraph interrupts / approval gates before destructive ops; review-then-merge PRs;
  confidence thresholds prioritize review effort.
- **MCP** (Anthropic, Nov 2024) — unified client-server protocol for tool/data access; adopters Zed,
  Replit, Codeium, Sourcegraph, Block, Apollo; Devin's MCP Marketplace. Eliminates N custom integrations.

**Deployments:** GitHub Copilot (150M devs, free tier Dec 2024); Cursor (½ of Fortune 500 — NVIDIA
40K engineers, Stripe, YC 80%); Devin/Cognition (GA Dec 2024; Mercedes-Benz, LTM, Cognizant, Infosys);
Claude Code CLI (MCP-native); Replit Agent; Bolt.new; v0 (Vercel). Open-source/research: SWE-agent
(Princeton; 65% SWE-bench Verified w/ Claude 3.7), Aider (44K★; 88% of its own last release
self-written), Sweep. **Benchmark:** Claude 3.5 Sonnet hit 49% on SWE-bench Verified (Oct 2024).

**Adoption:** 97% experimenting, 62% daily, but only ~9% fully deployed at scale (Accenture). Trust
gap — only 43% trust accuracy. 70% don't see AI as a job threat; ~100% think AI proficiency boosts
employability.

**Bottlenecks:** reliability on large repos (context limits, recursive stuck-loops), verification
(hidden-test problem → "bandaids"), cost (100+ turn convos $10–50/task), autonomous-execution security,
no cross-session learning by default, multimodal gaps, CI noise.

**India angle:** $250B+ IT-services labor-arbitrage model under pressure; firms deploying agents
*internally*; shift from "developer-hours" to "agent-augmented delivery"; retraining toward agent
orchestration/QA.

## 2. DevOps & SRE / incident response / observability
**Snapshot:** targets MTTR, alert fatigue, on-call burden. 91% less event noise, 75% less downtime
(PagerDuty customer data).
**Problems solved:** alert fatigue, MTTR (3× faster, RCA <3min), on-call burden, auto-postmortems,
runbook automation, NL→query (SPL/DQL/PromQL).
**Patterns:** hypothesis-driven debugging loop (triage→contextualize→hypothesize→test→iterate→
remediate); Honeycomb BubbleUp (sub-10s high-cardinality queries); Datadog Bits (autonomous
investigate→root-cause→remediate with visible reasoning); tool calling into observability + remediation
(2,000+ prebuilt actions); multi-agent teams under a coordinator; HITL before state-changing ops.
**Deployments:** PagerDuty AIOps+Advance (30K+ companies, 400%+ ROI; Zoom, Cox, DraftKings, TUI);
Datadog Bits AI; Splunk AI SRE (Rent the Runway: 94% faster MTTR); New Relic Autopilot; Honeycomb
(Intercom Fin case); CrowdStrike Charlotte (3× faster response, ISO 42001-certified).
**Bottlenecks:** emergent microservice behavior, noisy telemetry token budgets, trust in
auto-remediation, novel-incident coverage, legacy-tool integration.
**India:** NOC transformation (thousands of L1/L2 engineers → agent supervisors); Infosys/TCS building
proprietary AIOps; pricing shifts to "cost per incident resolved."

## 3. IT service management & internal IT support
**Problems solved:** Tier-1 tickets (password resets, provisioning), triage/routing, KB search,
provisioning workflows, self-service expansion.
**Patterns:** ticket classification→routing, knowledge RAG (Confluence/SharePoint/Slack), workflow
orchestration via ITSM APIs, graceful human escalation with context.
**Deployments:** ServiceNow Now Assist, Atlassian Jira Service Management AI, Microsoft Copilot Studio
— but public detail is thin (many deployments under NDA); mostly early pilots at Fortune 500.
**Bottlenecks:** approval-policy edge cases, scoped permissions, poor-escalation UX.
**India:** offshore support centers under automation pressure; pivot to agent+human hybrid.

## 4. Security operations (SOC / SecOps)
**Problems solved:** alert fatigue (90%+ false positives), triage bottleneck, threat hunting, IR
playbooks, vuln prioritization.
**Patterns:** trained on elite-analyst decisions; NL agent builders (CrowdStrike AgentWorks);
triage→enrich→investigate→recommend→execute-with-approval; GitGuardian detect→attribute→rotate→
remediate (<60s leak-to-notification).
**Deployments:** CrowdStrike Charlotte + Agentic SOAR (Blackbaud 30K invocations/3 days, 3× MTTR;
Mondelez; ISO 42001); Datadog Bits Security Analyst; GitGuardian (monitors Cursor/Copilot/Devin & MCP
servers for secret leaks; 5× more secrets remediated YoY).
**Bottlenecks:** false-negative risk of auto-filtering, adversarial evasion, audit-trail explainability,
legacy-SIEM integration.
**India:** LTM deploying Devin across a cybersecurity practice (260+ clients); CERTs adopting AI triage.

## 5. Data engineering / analytics agents
**Snapshot:** lags coding/DevOps — fewer named products, more frameworks.
**Problems solved:** NL→SQL, pipeline orchestration (Airflow/dbt), data-quality checks, RAG
construction, multimodal data curation.
**Patterns:** NL→SQL/Python ReAct over data; distributed pipelines (Ray/@ray.remote, batch embeddings
across GPU workers); agentic RAG (retrieve→generate→verify→re-retrieve, LangGraph).
**Deployments:** Snowflake Cortex, Databricks Lakehouse AI, Anyscale/Ray (Coinbase, Character.ai,
Physical Intelligence); LangGraph (Uber, LinkedIn, Klarna, Nvidia); Bedrock Agents.
**Bottlenecks:** complex business logic, data-quality accountability, distributed-compute cost, SQL
dialect variance.
**India:** analytics offshoring under threat → shift to "semantic-layer architects" and "RAG engineers."

## Cross-cutting meta-patterns (the synthesis worth memorizing)
1. **ACI > raw APIs** — design tools for agent ergonomics (SWE-agent's key insight).
2. **Reason before acting** — plan-first beats act-then-correct.
3. **Self-correction via feedback loops** — every action returns an observation; retry with refinement.
4. **Multi-agent > monolith** — specialized sub-agents under a supervisor.
5. **HITL for high-stakes actions** — approval gates for deploys/remediations/data changes.
6. **MCP as connective tissue** — standard tool protocol accelerating the ecosystem.
7. **Hybrid model routing** — cheap models for easy tasks, frontier for hard ones (cost control).

> **For Setu:** the ACI discipline (#1) is the most transferable idea — shape `pdf_extract`, `fx`,
> `calc`, `reconcile` with absolute-path-style error-proofing, exact-match semantics, and actionable
> error returns, so the orchestrator's ReAct loop self-corrects instead of flailing.
