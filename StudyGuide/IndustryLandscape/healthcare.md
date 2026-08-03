# Agentic AI in Healthcare & Life Sciences (2024–2026)

> **Why it matters to the landscape:** healthcare has the single most *commercially mature* agentic
> product category — **ambient clinical scribing** — and the clearest example of the "AI proposes,
> licensed human disposes" guardrail that Setu also relies on.

## 1. Clinical documentation & ambient scribing  *(most mature)*
**Snapshot:** physicians spend 40–60% of time on documentation. India's burden compounded by
1:1,445 physician ratio.
**Problems solved:** documentation time (1–2 hrs of notes per hr of care), burnout, delayed charts,
EHR friction, coding accuracy.
**Patterns:** multi-step conversation analysis (speech→transcript→structured note→coding→orders);
contextual reasoning pulling prior visits/labs/meds; pre-visit chart-review agents; deep EHR
integration (Epic/Oracle Health via HL7/FHIR); patient-specific memory over 100+ prior visits;
parallel agents (transcription/coding/reasoning/Q&A); **every note requires clinician sign-off** —
confabulation-elimination guardrails.
**Deployments:** Abridge (300+ health systems, 100M+ conversations/yr — Kaiser, Johns Hopkins, Mayo);
Nabla (85K+ clinicians, 20M+ encounters/yr); Nuance DAX / Microsoft Dragon; Suki (400+ systems);
DeepScribe (90% of community oncology); Commure (150+ systems). Outcomes: 83–86% note-effort
reduction, 17% cognitive-load drop (Mayo).
**Adoption:** early production, rapid scale — 95%+ retention (Abridge). Consolidating around 5–7 vendors.
**Bottlenecks:** confabulation, specialty accuracy variance, multi-speaker diarization, noisy
environments, integration depth, $300–500/clinician/mo cost, PHI privacy, trust.
**India gaps:** no India-native vendor, no Indian-language/medical-terminology models, <20% EHR
penetration, need $10–20/mo pricing, ASHA-worker tools absent. **Opportunities:** multilingual scribing,
private-chain targeting, eSanjeevani integration (300M+ teleconsults), mobile-first ASHA tools.

## 2. Clinical decision support & diagnostics triage
**Snapshot:** 5B+ radiology exams/yr globally, 250M+ in India; shortage of 60,000+ radiologists.
**Problems solved:** diagnostic delays for critical findings, radiologist shortage, missed diagnoses
(3–5% human → <1% AI), triage inefficiency, specialist access, coding under-capture.
**Patterns:** multi-step diagnostic reasoning (symptom→differential→workup→dx); retrospective chart
scanning (Regard); PACS/DICOM tool integration; medical-KB RAG (PubMed/UpToDate/guidelines); parallel
specialty agents on one scan; foundation models (Aidoc CARE, Paige Virchow); all findings need
clinician confirmation.
**Deployments:** Aidoc (1,600+ centers; 34% faster door-to-puncture for stroke); **Qure.ai** (5,500+
sites, 105+ countries, 45M+ lives, FDA-cleared; India stroke-care w/ Medtronic); Paige (pathology
foundation models on 1.5M+ slides); Regard ($50M+ revenue captured); Tempus; AMBOSS LiSA; Hippocratic
AI (1,000+ agents, validated on 725K test calls).
**Bottlenecks:** FDA Class-II multi-year cycles (CDSCO slower), Western-population training bias,
PACS/EHR silos, false-positive alert fatigue, black-box explainability, liability, $50–200K/algorithm/yr.
**India gaps:** <1% of imaging centers have AI, pathology AI absent, no mobile diagnostics for ASHA
devices, TB-screening under-deployed. **Opportunities:** NDHM-network radiology AI, India-specific
datasets, chain deployment, eSanjeevani triage, high-impact/low-cost modalities (chest X-ray, ECG,
fundus).

## 3. Hospital & administrative operations
**Snapshot:** US healthcare admin costs $1T+/yr (30% of spend); 2M+ billing/coding specialists.
**Problems solved:** prior-auth delays (7–14 days, 33% denials), revenue-cycle inefficiency, no-shows
(20–30%), claims denials ($262B/yr), staffing shortages, referral leakage.
**Patterns:** multi-step prior-auth (eligibility→documentation→submit→appeal); claims-scrubbing;
no-show-risk outreach; denial-management loops; payer/EHR/clearinghouse API integration; front→mid→
back-cycle agent coordination; HITL for complex appeals.
**Deployments:** Waystar (60% of US patients, AltitudeAI); Commure ($25B+ claims; Yale New Haven 54%
no-show reduction); Cohere Health; Notable; Rhapsody.
**Adoption:** early-mid; much is still RPA, agentic capabilities emerged 2024–25; concentrated in
500+-bed systems.
**Bottlenecks:** HIPAA autonomous-access limits, 1,000+ payers × quarterly rule changes, unstructured
docs, fragmented systems, 18–36mo ROI horizon.
**India gaps:** no India-native RCM AI (no Ayushman Bharat support), fragmented payers, cash-pay
dominance (60%+), low EHR. **Opportunities:** Ayushman Bharat-native prior-auth/claims (500M lives),
private-chain targeting, scheduling agents, ABDM standardization.

## 4. Drug discovery & life-sciences R&D
**Snapshot:** targets the >10-yr, $2B+, 90%-failure R&D pipeline; operates in-silico early on → more
amenable to autonomy.
**Problems solved:** target ID (3–5 yrs), molecule design (10^60 chemical space), preclinical failure,
trial enrollment, rare-disease economics, antibody design.
**Patterns:** hypothesis→in-silico→wet-lab→refine loops; active learning (AI proposes next experiments);
retrosynthetic planning; multi-objective optimization; HTS robotics + MD-simulation tool calls;
literature/AlphaFold RAG; target→lead→optimization→preclinical agent chain; chemist HITL before synthesis.
**Deployments:** Recursion (50PB data, BioHive-2; REC-4881 Phase 1b/2; acquired Exscientia); Insilico
Medicine; Absci (6-week data-to-validation); AlphaFold (200M+ structures).
**Adoption:** pilot→early production, "trough of disillusionment" — ~30 AI-designed candidates in
trials (up from ~5 in 2023), **zero approved yet**; validation won't be clear until 2027–2030.
**Bottlenecks:** no FDA AI-drug pathway, sim-to-real gap (40–60% validation), biological complexity,
data scarcity vs web-scale, $10–100M compute, Phase II/III still 80% of cost.
**India gaps:** no AI-drug unicorns, no pharma supercomputers, data deserts, CDSCO capacity, talent
drain. **Opportunities:** generics/biosimilar formulation, India-relevant diseases (TB 28% global
burden, snakebite), CSIR/IIT open-source, cheaper trials.

## 5. Patient-facing care navigation & telemedicine
**Snapshot:** US 2M+ call-center workers; India 1M+ ASHA workers, 300M+ eSanjeevani teleconsults.
**Problems solved:** rural access, symptom triage, medication adherence (50% non-adherence),
post-discharge follow-up (20% readmissions), scheduling, health literacy.
**Patterns:** symptom→differential→triage→escalate loops; adherence-monitoring loops; motivational-
interviewing; EHR/scheduling/pharmacy/SMS-WhatsApp tool integration; **strict no-diagnosis/no-
prescribe guardrails**; red-flag escalation; nurse oversight for high-risk.
**Deployments:** Hippocratic AI (1,000+ agents, Polaris architecture; 30% readmission reduction, 12×
ROI); Buoy Health; K Health; Limbic; Curai; eSanjeevani (300M+ consults, human-driven).
**Adoption:** US early production in narrow use cases; India huge scale but low-AI.
**Bottlenecks:** safety-critical missed-red-flag risk, low-resource-language models, noisy-line voice,
first-user personalization, Western-norm cultural bias, reimbursement, no India regulatory framework
(misinformation risk).
**India gaps:** no ASHA-agent integration, no validated vernacular symptom checkers, eSanjeevani
un-augmented, rural connectivity, unregulated WhatsApp health bots. **Opportunities:** eSanjeevani
triage pre-screen, vernacular checkers grounded in rural disease prevalence, ASHA copilots, PMJAY
post-discharge follow-up, maternal health, chronic-disease adherence.

## Cross-cutting
**Patterns:** foundation models + domain adaptation (Med-PaLM, Virchow, CARE) · **RAG dominance**
(hallucination risk makes it near-universal) · tool/function calling (MCP emerging, Rhapsody) ·
multi-agent orchestration · HITL ("AI proposes, human disposes") · safety guardrails (input/output
validation, bias monitoring, hallucination detection, audit trails).
**Maturity:** docs (most mature) > radiology triage > hospital ops > patient-facing (fragmented) >
drug discovery (hype > reality, no approved drug yet).
**Regulation:** SaMD (diagnostic, multi-year) vs CDS exemption (advisory) vs no-device (docs, fast).
Liability is unresolved ("learned intermediary" doctrine).
**India strategic position:** leapfrog (low legacy) + massive need + 10× cost constraint ($10–20/mo)
+ talent + regulatory vacuum (opportunity *and* risk). Success factors: multilingual, mobile-first,
offline-capable, affordable, government partnership, cultural adaptation, ASHA integration.
