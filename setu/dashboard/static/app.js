const state = {
  overview: null,
  policies: [],
  sources: [],
  allocationView: "asset_class",
  requestToken: null
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
}

function money(value, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency, maximumFractionDigits: 0
  }).format(Number(value || 0));
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

async function fetchJson(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    window.location.replace("/login");
    throw new Error("Dashboard session expired.");
  }
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try { message = (await response.json()).detail || message; } catch (_error) { /* response was not JSON */ }
    throw new Error(message);
  }
  return response.json();
}

async function loadDashboard() {
  try {
    const [overview, agents, activity, ingestions, policies, sources, session] = await Promise.all([
      fetchJson("/api/overview"), fetchJson("/api/agents"), fetchJson("/api/activity"),
      fetchJson("/api/ingestions"),
      fetchJson("/api/policies"),
      fetchJson("/api/sources"),
      state.requestToken ? Promise.resolve(null) : fetchJson("/api/session")
    ]);
    if (session) state.requestToken = session.request_token;
    state.overview = overview;
    state.policies = policies.policies;
    state.sources = sources.sources;
    renderOverview(overview);
    renderAgents(agents.agents);
    renderActivity(activity.events);
    renderIngestions(ingestions.runs);
    renderPolicies(policies.policies);
    renderSources(sources);
  } catch (error) {
    showToast("Setu could not read the local ledger.");
    console.error(error);
  }
}

async function loadIngestions() {
  try {
    const ingestions = await fetchJson("/api/ingestions");
    renderIngestions(ingestions.runs);
  } catch (error) {
    console.error(error);
  }
}

function renderOverview(data) {
  $("#net-worth").textContent = money(data.net_worth, data.base_currency);
  $("#account-count").textContent = data.counts.accounts;
  $("#holding-count").textContent = data.counts.holdings;
  $("#policy-count").textContent = data.counts.policies;
  renderAllocation();
    renderPerformance(data.performance, data.base_currency);
    renderInsights(data.insights || []);
    renderHealth(data.health);
    renderPositions(data.positions, data.base_currency);
  renderRisk(data);
}

function renderAllocation() {
  const values = state.overview?.allocation?.[state.allocationView] || {};
  const total = Object.values(values).reduce((sum, value) => sum + Number(value), 0);
  const rows = Object.entries(values).sort((a, b) => Number(b[1]) - Number(a[1]));
  $("#allocation-bars").innerHTML = rows.length ? rows.map(([label, value]) => {
    const fraction = total ? Number(value) / total : 0;
    return `<div class="allocation-row">
      <span class="allocation-label" title="${escapeHtml(label)}">${escapeHtml(prettyLabel(label))}</span>
      <div class="allocation-track"><div class="allocation-fill" style="width:${Math.max(fraction * 100, 1)}%"></div></div>
      <span class="allocation-value">${percent(fraction)}</span>
    </div>`;
  }).join("") : '<p class="empty">No valued positions yet.</p>';
}

function renderPositions(positions, baseCurrency) {
  $("#position-count").textContent = `${positions.length} position${positions.length === 1 ? "" : "s"}`;
  $("#positions-body").innerHTML = positions.length ? positions.map(position => `<tr>
    <td><span class="position-name">${escapeHtml(position.label)}</span>${position.kind === "insurance" ? '<span class="position-kind">Policy</span>' : ""}</td>
    <td>${escapeHtml(prettyLabel(position.asset_class))}</td>
    <td>${escapeHtml(prettyLabel(position.geography))}</td>
    <td class="number">${escapeHtml(money(position.base_value, baseCurrency))}</td>
    <td class="number">${position.base_cost_basis == null ? "—" : escapeHtml(money(position.base_cost_basis, baseCurrency))}</td>
    <td class="number">${position.unrealized_gain == null ? "—" : `<span class="${Number(position.unrealized_gain) >= 0 ? "gain" : "loss"}">${escapeHtml(money(position.unrealized_gain, baseCurrency))}<small>${escapeHtml(percent(position.roi_fraction))}</small></span>`}</td>
  </tr>`).join("") : '<tr><td colspan="6" class="empty">Import a statement to create your first position.</td></tr>';
}

function renderPerformance(performance, baseCurrency) {
  const status = performance?.status || "unavailable";
  if (status !== "available") {
    $("#roi-status").textContent = "Not available";
    $("#performance-metrics").innerHTML = '<p class="empty">No imported investment currently has a source-stated cost basis. Setu will not estimate ROI.</p>';
    $("#performance-note").textContent = "Upload a statement that includes cost basis, book value, or invested amount.";
    return;
  }
  const gain = Number(performance.unrealized_gain);
  $("#roi-status").textContent = `${performance.covered_positions}/${performance.total_positions} positions covered`;
  $("#performance-metrics").innerHTML = [
    ["Current value", money(performance.current_value, baseCurrency)],
    ["Cost basis", money(performance.cost_basis, baseCurrency)],
    ["Unrealized gain", money(performance.unrealized_gain, baseCurrency)],
    ["ROI", percent(performance.roi_fraction)]
  ].map(([label, value], index) => `<div class="performance-stat ${index > 1 ? (gain >= 0 ? "gain" : "loss") : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("#performance-note").textContent = `${percent(performance.coverage_fraction)} of investment value has source-backed cost. Cash, insurance, fees, taxes, and distributions are excluded.`;
}

function renderInsights(insights) {
  $("#insight-count").textContent = `${insights.length} signal${insights.length === 1 ? "" : "s"}`;
  $("#insight-list").innerHTML = insights.length ? insights.map(insight => `<article class="insight-item ${escapeHtml(insight.severity)}">
    <span class="insight-severity">${escapeHtml(prettyLabel(insight.severity))}</span>
    <strong>${escapeHtml(insight.title)}</strong>
    <p>${escapeHtml(insight.detail)}</p>
  </article>`).join("") : '<p class="empty">Add portfolio data to generate grounded signals.</p>';
}

function renderHealth(health) {
  const container = $("#health-content");
  if (!health || health.label === "Insufficient data") {
    $("#health-as-of").textContent = "Insufficient data";
    container.innerHTML = '<p class="empty">Add valued positions and a declared risk profile to calculate an explainable health score.</p>';
    return;
  }
  $("#health-as-of").textContent = `As of ${health.as_of}`;
  const horizons = ["current", "short_term", "long_term"]
    .map(key => health.horizons?.[key])
    .filter(Boolean);
  const components = health.components || [];
  const actions = health.actions || [];
  const missing = health.missing_data || [];
  container.innerHTML = `
    <div class="health-overview">
      <div class="health-score ${escapeHtml(health.horizons?.current?.status || "watch")}">
        <strong>${escapeHtml(health.score)}</strong><span>/100</span>
      </div>
      <div><p class="health-label">${escapeHtml(health.label)}</p><p class="health-method">${escapeHtml(health.methodology)}</p></div>
    </div>
    <div class="horizon-grid">
      ${horizons.map(horizon => `<article class="horizon-item ${escapeHtml(horizon.status)}">
        <span>${escapeHtml(prettyLabel(horizon.status))}</span>
        <strong>${escapeHtml(horizon.title)}</strong>
        <p>${escapeHtml(horizon.detail)}</p>
      </article>`).join("")}
    </div>
    <div class="health-detail-grid">
      <section>
        <h3>Score breakdown</h3>
        <div class="health-components">${components.map(component => `<div class="health-component">
          <div><strong>${escapeHtml(component.label)}</strong><span>${escapeHtml(component.score)} / ${escapeHtml(component.max_score)}</span></div>
          <div class="health-track"><span class="${escapeHtml(component.status)}" style="width:${Math.max(3, Number(component.score) / Number(component.max_score || 1) * 100)}%"></span></div>
          <p>${escapeHtml(component.detail)}</p>
        </div>`).join("")}</div>
      </section>
      <section>
        <h3>Review next</h3>
        <ol class="health-actions">${actions.map(action => `<li><strong>${escapeHtml(action.title)}</strong><span>${escapeHtml(action.detail)}</span></li>`).join("")}</ol>
        <h3 class="missing-title">Still missing</h3>
        <ul class="health-missing">${missing.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </section>
    </div>`;
}

function renderRisk(data) {
  const profile = data.risk_profile;
  if (!profile || !Number(data.net_worth)) {
    $("#risk-content").innerHTML = '<p class="empty">Set a risk profile to compare actual and target allocation.</p>';
    return;
  }
  $("#profile-label").textContent = profile.label;
  const total = Number(data.net_worth);
  const classes = data.allocation.asset_class;
  const metrics = [
    ["Equity", Number(classes.EQUITY || 0) / total, Number(profile.target_equity)],
    ["Debt", Number(classes.DEBT || 0) / total, Number(profile.target_debt)],
    ["Cash", Number(classes.CASH || 0) / total, Number(profile.target_cash)]
  ];
  $("#risk-content").innerHTML = metrics.map(([label, actual, target]) => `<div class="risk-row">
    <div class="risk-label"><strong>${label}</strong><span>${percent(actual)} actual / ${percent(target)} target</span></div>
    <div class="risk-track"><div class="risk-actual" style="width:${Math.min(actual * 100,100)}%"></div><div class="risk-target" style="left:${Math.min(target * 100,100)}%"></div></div>
  </div>`).join("") + '<p class="risk-note">The orange marker is your target. Setu reports drift; it does not trade or rebalance automatically.</p>';
}

function renderAgents(agents) {
  $("#agent-nav").innerHTML = agents.map((agent, index) => `<button class="agent-link ${agent.status === "active" ? "active" : "planned"}" type="button" data-agent="${escapeHtml(agent.id)}" data-status="${escapeHtml(agent.status)}">
    <span class="agent-icon">${escapeHtml(agent.name.charAt(0))}</span>
    <span>${escapeHtml(agent.name.replace(" Agent", ""))}</span>
    <span class="agent-status">${agent.status === "active" ? "Active" : "Soon"}</span>
  </button>`).join("");
  $$(".agent-link").forEach(button => button.addEventListener("click", () => {
    if (button.dataset.status !== "active") showToast(`${button.textContent.trim().replace("Soon", "")} workspace is planned next.`);
  }));
}

function renderActivity(events) {
  $("#activity-list").innerHTML = events.length ? events.map(event => `<article class="activity-item">
    <span class="activity-dot" aria-hidden="true"></span>
    <p class="activity-title">${escapeHtml(event.title)}</p>
    <p class="activity-meta">${escapeHtml(event.source)} · period ${escapeHtml(event.period_end)} · ${escapeHtml(event.status)}</p>
  </article>`).join("") : '<p class="empty">No documents have been imported yet.</p>';
}

function renderIngestions(runs) {
  const reviews = runs.filter(run => run.status === "review");
  $("#review-count").textContent = reviews.length;
  $("#review-list").innerHTML = reviews.map(run => `<article class="review-card">
    <strong>${escapeHtml(run.source_name)}</strong>
    <span>${escapeHtml(prettyLabel(run.document_kind || "document"))} · validation needs review</span>
    <p class="review-question">${escapeHtml(run.question || "Setu needs your decision before writing to the ledger.")}</p>
    <div class="review-actions">
      ${run.allow_accept ? `<button class="accept" type="button" data-decision="accept" data-run-id="${escapeHtml(run.id)}">Accept</button>` : ""}
      <button type="button" data-decision="reject" data-run-id="${escapeHtml(run.id)}">Reject</button>
    </div>
  </article>`).join("");

  $("#run-list").innerHTML = runs.length ? runs.slice(0, 8).map(run => {
    const result = run.status === "completed" && run.reconcile_status === "duplicate"
      ? "Already imported · existing policy retained"
      : run.status === "completed"
      ? `${run.persisted_holdings} holdings · ${run.persisted_balances || 0} balances · ${run.persisted_policies} policies · ${run.persisted_obligations} obligations`
      : run.status === "review" ? "Waiting for your decision" : prettyLabel(run.status);
    return `<article class="run-item">
      <span class="run-state ${escapeHtml(run.status)}" aria-hidden="true"></span>
      <div><p class="run-title">${escapeHtml(run.source_name)}</p>
      <p class="run-meta">${escapeHtml(prettyLabel(run.document_kind || "detecting"))} · ${escapeHtml(result)}</p>
      ${run.error ? `<p class="run-error">${escapeHtml(run.error)}</p>` : ""}</div>
    </article>`;
  }).join("") : '<p class="empty">No dashboard imports yet.</p>';

  $$('[data-decision]').forEach(button => button.addEventListener("click", () => submitDecision(
    button.dataset.runId,
    button.dataset.decision,
    button
  )));
  renderSourceUploads(runs);
}

function sourceRecordSummary(records) {
  const labels = [
    [records.holdings, "holding"],
    [records.balances, "balance"],
    [records.policies, "policy"],
    [records.obligations, "obligation"],
    [records.transactions, "transaction"]
  ];
  const populated = labels
    .filter(([count]) => Number(count))
    .map(([count, label]) => `${count} ${label}${Number(count) === 1 ? "" : "s"}`);
  return populated.join(" · ") || "No portfolio records";
}

function renderSources(data) {
  const sources = data.sources || [];
  const activeCount = Number(data.active_count || 0);
  $("#source-count").textContent = `${activeCount} active / ${sources.length} source${sources.length === 1 ? "" : "s"}`;
  $("#source-list").innerHTML = sources.length ? sources.map(source => {
    const statusLabel = source.status === "included"
      ? "Used in portfolio"
      : source.status === "available"
      ? "Active, not current"
      : "Inactive";
    return `<article class="source-item ${source.active ? "" : "inactive"}">
      <div class="source-identity">
        <strong>${escapeHtml(source.file_name)}</strong>
        <span>${escapeHtml(source.institution)} · ${escapeHtml(prettyLabel(source.document_kind))}</span>
      </div>
      <div class="source-evidence">
        <strong>${escapeHtml(sourceRecordSummary(source.records))}</strong>
        <span>Statement period ${escapeHtml(formatDate(source.period_end))}</span>
      </div>
      <span class="source-status ${escapeHtml(source.status)}">${escapeHtml(statusLabel)}</span>
      <label class="source-switch">
        <input type="checkbox" data-source-toggle="${source.id}" ${source.active ? "checked" : ""} aria-label="Use ${escapeHtml(source.file_name)} in portfolio">
        <span class="source-switch-track" aria-hidden="true"><span></span></span>
        <span class="source-switch-label">${source.active ? "Active" : "Inactive"}</span>
      </label>
    </article>`;
  }).join("") : '<p class="empty">No imported source documents yet. Import a PDF to create a controllable source.</p>';

  const unlinked = data.unlinked_records || {};
  const unlinkedNote = $("#unlinked-source-note");
  if (Number(unlinked.total || 0)) {
    unlinkedNote.textContent = `${unlinked.total} legacy or synthetic record${Number(unlinked.total) === 1 ? " is" : "s are"} not linked to an uploaded file and remain included.`;
    unlinkedNote.hidden = false;
  } else {
    unlinkedNote.hidden = true;
  }

  $$('[data-source-toggle]').forEach(input => input.addEventListener("change", () => updateSource(
    input.dataset.sourceToggle,
    input.checked,
    input
  )));
}

function renderSourceUploads(runs) {
  const exceptional = runs.filter(run => (
    run.status !== "completed" || run.reconcile_status === "duplicate"
  )).slice(0, 8);
  const section = $("#source-upload-section");
  if (!exceptional.length) {
    section.hidden = true;
    $("#source-upload-list").innerHTML = "";
    return;
  }
  section.hidden = false;
  $("#source-upload-list").innerHTML = exceptional.map(run => `<div class="source-upload-item">
    <span class="run-state ${escapeHtml(run.status)}" aria-hidden="true"></span>
    <div><strong>${escapeHtml(run.source_name)}</strong><span>${escapeHtml(prettyLabel(run.reconcile_status === "duplicate" ? "duplicate" : run.status))}</span></div>
  </div>`).join("");
}

async function updateSource(sourceId, active, input) {
  input.disabled = true;
  try {
    await fetchJson(`/api/sources/${encodeURIComponent(sourceId)}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-Setu-Request-Token": state.requestToken
      },
      body: JSON.stringify({ active })
    });
    showToast(active ? "Source activated. Portfolio recalculated." : "Source inactive. Its records are now excluded.");
    await loadDashboard();
  } catch (error) {
    input.checked = !active;
    input.disabled = false;
    showToast(error.message);
  }
}

function renderPolicies(policies) {
  $("#policy-list-count").textContent = `${policies.length} polic${policies.length === 1 ? "y" : "ies"}`;
  $("#policy-list").innerHTML = policies.length ? policies.map(policy => {
    const warning = policy.quality_status !== "verified";
    const qualityLabel = policy.quality_status === "partial" ? "Partial evidence" : warning ? "Needs review" : "Verified";
    return `<article class="policy-summary ${warning ? "needs-review" : ""}">
      <div class="policy-summary-head">
        <div><h3>${escapeHtml(policy.policy_name)}</h3><p class="policy-insurer">${escapeHtml(policy.insurer)} · ${escapeHtml(prettyLabel(policy.policy_type))}</p></div>
        <span class="quality-pill ${warning ? "needs-review" : ""}">${qualityLabel}</span>
      </div>
      <div class="policy-facts">
        <div class="policy-fact"><span>Coverage</span><strong>${escapeHtml(optionalMoney(policy.sum_assured, policy.currency))}</strong></div>
        <div class="policy-fact"><span>Current asset value</span><strong>${escapeHtml(optionalMoney(policy.asset_value, policy.currency))}</strong></div>
        <div class="policy-fact"><span>Premium</span><strong>${escapeHtml(optionalMoney(policy.premium_amount, policy.premium_currency || policy.currency))}</strong></div>
        <div class="policy-fact"><span>Maturity outlook</span><strong>${escapeHtml(policyMaturitySummary(policy))}</strong></div>
      </div>
      <div class="policy-summary-foot">
        <p class="policy-warning-inline">${warning ? escapeHtml(policy.quality_issues[0]) : escapeHtml(valuationExplanation(policy))}</p>
        <button class="detail-button" type="button" data-policy-id="${policy.id}">View details</button>
      </div>
    </article>`;
  }).join("") : '<p class="empty">No insurance policies have been added.</p>';
  $$('[data-policy-id]').forEach(button => button.addEventListener("click", () => {
    const policy = state.policies.find(item => String(item.id) === button.dataset.policyId);
    if (policy) openPolicyDetails(policy);
  }));
}

function optionalMoney(value, currency) {
  return value === null || value === undefined ? "Not available" : money(value, currency);
}

function policyMaturitySummary(policy) {
  const projection = policy.projection || {};
  if (["calculated_plan_rule", "stated"].includes(projection.status) && projection.amount !== undefined) {
    return money(projection.amount, policy.currency);
  }
  if (projection.status === "official_scenarios") {
    return `${money(projection.lower_amount, policy.currency)}–${money(projection.upper_amount, policy.currency)}`;
  }
  if (projection.status === "not_applicable") return "Not applicable";
  return "Needs evidence";
}

function formatDate(value) {
  if (!value) return "Not available";
  const date = new Date(`${value.length === 10 ? value + "T00:00:00" : value}`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "short", day: "numeric"
  }).format(date);
}

function valuationExplanation(policy) {
  if (policy.policy_type === "TERM") return "Protection coverage; correctly excluded from net worth.";
  if (policy.asset_value === null || policy.asset_value === undefined) return "Current cash value was not provided, so Setu excludes it from net worth.";
  if (policy.policy_type === "ULIP") return "Current fund value contributes to net worth.";
  return "Current stated policy value contributes to net worth.";
}

function projectionMarkup(policy) {
  const projection = policy.projection || { status: "insufficient_evidence", missing_fields: [] };
  if (projection.status === "official_scenarios") {
    return `<div class="detail-grid">
      ${detailField("4% illustration", money(projection.lower_amount, policy.currency))}
      ${detailField("8% illustration", money(projection.upper_amount, policy.currency))}
    </div><p class="detail-explanation">These are the official lower and upper illustration scenarios. They are not guaranteed returns.</p>`;
  }
  if (projection.status === "stated") {
    return `<div class="detail-grid">${detailField("Stated maturity value", money(projection.amount, policy.currency))}${detailField("Basis", projection.method)}</div>`;
  }
  if (projection.status === "calculated_plan_rule") {
    return `<div class="detail-grid">
      ${detailField("Grounded maturity amount", money(projection.amount, policy.currency))}
      ${detailField("Base maturity (40%)", money(projection.base_maturity_amount, policy.currency))}
      ${detailField("Declared bonus / additions", money(projection.declared_bonus_additions, policy.currency))}
      ${detailField("Earlier scheduled money-back benefits", money(projection.scheduled_prior_benefits, policy.currency))}
      ${detailField("Grounded lifetime benefits", money(projection.grounded_lifetime_benefits, policy.currency))}
      ${detailField("Rule", projection.rule_source)}
    </div>
    <p class="detail-explanation">Future bonuses and any Final Additional Bonus are not included. This calculation depends on the policy remaining in force and the listed assumptions being true.</p>
    <div class="quality-alert"><strong>Assumptions to verify</strong><ul>${(projection.assumptions || []).map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`;
  }
  if (projection.status === "not_applicable") {
    return `<p class="detail-explanation">${escapeHtml(projection.method)}</p>`;
  }
  const missing = projection.missing_fields || [];
  return `<div class="quality-alert"><strong>Maturity projection needs more evidence</strong><ul>${missing.map(field => `<li>${escapeHtml(field)}</li>`).join("")}</ul></div><p class="detail-explanation">Setu will not compound premiums or guess future bonuses. Upload the LIC policy schedule, bonus statement, or signed benefit illustration.</p>`;
}

function detailField(label, value) {
  return `<div class="detail-field"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function openPolicyDetails(policy) {
  const warning = policy.quality_status !== "verified";
  $("#policy-detail").innerHTML = `<div class="policy-detail-head">
    <div><p class="eyebrow">Insurance policy</p><h2 id="policy-dialog-title">${escapeHtml(policy.policy_name)}</h2><p>${escapeHtml(policy.insurer)} · ${escapeHtml(prettyLabel(policy.policy_type))}</p></div>
    <button class="dialog-close" id="policy-close" type="button" aria-label="Close policy details">×</button>
  </div>
  ${warning ? `<div class="quality-alert"><strong>This record needs verification</strong><ul>${policy.quality_issues.map(issue => `<li>${escapeHtml(issue)}</li>`).join("")}</ul></div>` : ""}
  <section class="detail-section"><h3>Coverage and value</h3><div class="detail-grid">
    ${detailField("Policy type", prettyLabel(policy.policy_type))}
    ${detailField("Coverage / sum assured", optionalMoney(policy.sum_assured, policy.currency))}
    ${detailField("Current asset value", optionalMoney(policy.asset_value, policy.currency))}
    ${detailField("Valuation basis", prettyLabel(policy.valuation_basis))}
  </div><p class="detail-explanation">${escapeHtml(valuationExplanation(policy))}</p></section>
  <section class="detail-section"><h3>Maturity outlook</h3>${projectionMarkup(policy)}</section>
  <section class="detail-section"><h3>Policy schedule</h3><div class="detail-grid">
    ${detailField("Plan number", policy.plan_number || "Not available")}
    ${detailField("Policy status", policy.status || "Not available")}
    ${detailField("Commencement date", formatDate(policy.commencement_date))}
    ${detailField("Maturity date", formatDate(policy.maturity_date))}
    ${detailField("Policy term", policy.policy_term_years ? `${policy.policy_term_years} years` : "Not available")}
    ${detailField("Premium payment term", policy.premium_payment_term_years ? `${policy.premium_payment_term_years} years` : "Not available")}
  </div></section>
  <section class="detail-section"><h3>Premium</h3><div class="detail-grid">
    ${detailField("Premium amount", optionalMoney(policy.premium_amount, policy.premium_currency || policy.currency))}
    ${detailField("Due date", formatDate(policy.premium_due_date))}
    ${detailField("Recurring", policy.premium_recurring ? "Yes" : "No")}
    ${detailField("Policy value as of", formatDate(policy.as_of_date))}
  </div></section>
  <section class="detail-section"><h3>Source and validation</h3><div class="detail-grid">
    ${detailField("Source document", policy.source_name || "Not available")}
    ${detailField("Imported", formatDate(policy.ingested_at))}
    ${detailField("Validation", policy.quality_status === "partial" ? "Partial evidence" : warning ? "Needs review" : "Verified")}
    ${detailField("Currency", policy.currency)}
    ${policy.extracted_policy_name !== policy.policy_name ? detailField("Originally extracted name", policy.extracted_policy_name) : ""}
  </div></section>
  <div class="policy-detail-actions"><button class="button primary" id="policy-done" type="button">Done</button></div>`;
  const dialog = $("#policy-dialog");
  dialog.showModal();
  $("#policy-close").addEventListener("click", () => dialog.close());
  $("#policy-done").addEventListener("click", () => dialog.close());
}

async function submitDecision(runId, decision, button) {
  button.disabled = true;
  try {
    await fetchJson(`/api/ingestions/${encodeURIComponent(runId)}/decision`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Setu-Request-Token": state.requestToken
      },
      body: JSON.stringify({ decision })
    });
    showToast(decision === "accept" ? "Review accepted. Setu is updating the ledger." : "Import rejected. Nothing was added.");
    await loadIngestions();
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
  }
}

function prettyLabel(value) {
  return String(value).replaceAll("_", " ").toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase());
}

let toastTimer;
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function connectActivity() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws/activity`);
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.type === "ledger_changed") loadDashboard();
  });
  socket.addEventListener("close", event => {
    if (event.code === 4401) {
      window.location.replace("/login");
      return;
    }
    setTimeout(connectActivity, 4000);
  });
}

const importDialog = $("#import-dialog");
const importForm = $("#import-form");
const fileInput = $("#document-file");
const dropZone = $("#drop-zone");
const askDialog = $("#ask-dialog");
const askForm = $("#ask-form");

function closeImportDialog() {
  importDialog.close();
  importForm.reset();
  $("#selected-file").hidden = true;
  $("#import-error").hidden = true;
}

function showSelectedFile(file) {
  const selected = $("#selected-file");
  selected.textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  selected.hidden = false;
  $("#import-error").hidden = true;
}

$("#import-button").addEventListener("click", () => importDialog.showModal());
$("#import-close").addEventListener("click", closeImportDialog);
$("#import-cancel").addEventListener("click", closeImportDialog);
fileInput.addEventListener("change", () => { if (fileInput.files[0]) showSelectedFile(fileInput.files[0]); });
["dragenter", "dragover"].forEach(type => dropZone.addEventListener(type, event => {
  event.preventDefault();
  dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach(type => dropZone.addEventListener(type, event => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
}));
dropZone.addEventListener("drop", event => {
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  showSelectedFile(file);
});
importDialog.addEventListener("click", event => {
  if (event.target === importDialog) closeImportDialog();
});
$("#policy-dialog").addEventListener("click", event => {
  if (event.target === $("#policy-dialog")) $("#policy-dialog").close();
});
$("#ask-button").addEventListener("click", () => {
  $("#ask-error").hidden = true;
  $("#ask-answer").hidden = true;
  askDialog.showModal();
  $("#ask-question").focus();
});
function closeAskDialog() {
  askDialog.close();
  askForm.reset();
  $("#ask-error").hidden = true;
  $("#ask-answer").hidden = true;
}
$("#ask-close").addEventListener("click", closeAskDialog);
$("#ask-cancel").addEventListener("click", closeAskDialog);
askDialog.addEventListener("click", event => {
  if (event.target === askDialog) closeAskDialog();
});
askForm.addEventListener("submit", async event => {
  event.preventDefault();
  const question = $("#ask-question").value.trim();
  const error = $("#ask-error");
  const answer = $("#ask-answer");
  if (question.length < 3) {
    error.textContent = "Enter a portfolio question.";
    error.hidden = false;
    return;
  }
  const submit = $("#ask-submit");
  submit.disabled = true;
  submit.textContent = "Analyzing…";
  error.hidden = true;
  answer.hidden = true;
  try {
    const result = await fetchJson("/api/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Setu-Request-Token": state.requestToken
      },
      body: JSON.stringify({ question })
    });
    const toolsUsed = Array.isArray(result.tools_used) ? result.tools_used : [];
    const fallbackAnswer = `<p>${escapeHtml(result.answer).replaceAll("\n", "<br>")}</p>`;
    const renderedAnswer = result.answer_format === "commonmark" && result.answer_html
      ? result.answer_html
      : fallbackAnswer;
    const truncationNotice = result.truncated
      ? `<p class="ask-limit-warning">This answer reached Setu's ${escapeHtml(result.limits?.max_output_tokens || "configured")} token limit. Ask a narrower follow-up for the missing detail.</p>`
      : "";
    answer.innerHTML = `
      <div class="ask-answer-head">
        <strong class="ask-answer-label">Setu</strong>
        <span class="ask-answer-format">Grounded answer</span>
      </div>
      <div class="ask-response">${renderedAnswer}</div>
      ${truncationNotice}
      <div class="ask-answer-meta">
        <span>${escapeHtml(result.privacy)}</span>
        ${toolsUsed.length ? `<span>Grounded by: ${escapeHtml(toolsUsed.map(prettyLabel).join(", "))}</span>` : ""}
      </div>`;
    answer.hidden = false;
  } catch (askError) {
    error.textContent = askError.message;
    error.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = "Ask";
  }
});
importForm.addEventListener("submit", async event => {
  event.preventDefault();
  const file = fileInput.files[0];
  const error = $("#import-error");
  if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
    error.textContent = "Choose a PDF document.";
    error.hidden = false;
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    error.textContent = "The PDF must be 25 MB or smaller.";
    error.hidden = false;
    return;
  }
  const submit = $("#import-submit");
  submit.disabled = true;
  submit.textContent = "Uploading…";
  try {
    const body = new FormData();
    body.append("file", file);
    await fetchJson("/api/ingestions", {
      method: "POST",
      headers: { "X-Setu-Request-Token": state.requestToken },
      body
    });
    closeImportDialog();
    showToast("Import started. Setu will request review if anything is uncertain.");
    await loadIngestions();
  } catch (uploadError) {
    error.textContent = uploadError.message;
    error.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = "Start import";
  }
});

$("#refresh-button").addEventListener("click", () => { loadDashboard(); showToast("Dashboard refreshed."); });
$("#logout-button").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    if (!state.requestToken) {
      state.requestToken = (await fetchJson("/api/session")).request_token;
    }
    await fetchJson("/api/auth/logout", {
      method: "POST",
      headers: { "X-Setu-Request-Token": state.requestToken }
    });
  } finally {
    window.location.replace("/login");
  }
});
$$('[data-planned]').forEach(button => button.addEventListener("click", () => showToast(`${button.dataset.planned} will be added in the next UI slice.`)));
$$('[data-allocation]').forEach(button => button.addEventListener("click", () => {
  state.allocationView = button.dataset.allocation;
  $$('[data-allocation]').forEach(item => item.classList.toggle("active", item === button));
  renderAllocation();
}));

loadDashboard();
connectActivity();
setInterval(loadIngestions, 2500);
