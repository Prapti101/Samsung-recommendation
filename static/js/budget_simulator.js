/* budget_simulator.js — USP: Budget Simulator card on the results page.
 *
 * The slider / number input represent a BUDGET CHANGE (+/-) applied to the
 * user's ORIGINAL budget — not a brand-new budget request. Only when the user
 * clicks "Update Recommendation" do we compute:
 *
 *     simulated_budget = original_budget + budget_change
 *
 * and call /api/simulate-budget, which re-runs the SAME server-side
 * recommendation engine (same persona / weights / priorities) filtered to
 * phones within the simulated budget, and returns a fresh Top 3. The
 * simulated results are shown below the original results, which never change.
 *
 * The comparison is always Original #1 vs Simulated #1 — previous simulations
 * are never cached or reused. No phone data, prices or reasons are hardcoded
 * here; every value shown comes from the server response.
 */

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("gm-budget-sim");
  if (!root) return;

  const slider = document.getElementById("sim-budget-slider");
  const input = document.getElementById("sim-budget-input");
  const updateBtn = document.getElementById("sim-update-btn");
  const changeDisplay = document.getElementById("sim-change-display");
  const budgetDisplay = document.getElementById("sim-budget-display");
  const resultEl = document.getElementById("gm-sim-result");
  const dataEl = document.getElementById("gm-budget-sim-data");

  function parseJsonScript(el, fallback) {
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent);
    } catch (_) {
      return fallback;
    }
  }

  const initData = parseJsonScript(dataEl, {});
  const weights = initData.weights || {};
  // The base budget the change is applied to, and the original #1 pick we
  // always compare the simulated result against. Both are fixed for the page.
  //
  // Resolve the original budget robustly: prefer the JSON data block, then the
  // data-* attribute on the card, then infer it from the slider bounds
  // (base = catalog_min - slider_min). We must NEVER fall back to 0, or the
  // recommendation engine would treat the budget as "unset" and rank the whole
  // catalog, making simulations look unchanged.
  function resolveOriginalBudget() {
    const fromJson = Number(initData.original_budget);
    if (Number.isFinite(fromJson) && fromJson > 0) return fromJson;

    const fromAttr = Number(root.getAttribute("data-original-budget"));
    if (Number.isFinite(fromAttr) && fromAttr > 0) return fromAttr;

    // Infer from slider: min attribute == (catalog_min - original_budget).
    const catalogMin = Number(root.getAttribute("data-min-budget"));
    if (slider && Number.isFinite(catalogMin)) {
      const inferred = catalogMin - parseInt(slider.min, 10);
      if (Number.isFinite(inferred) && inferred > 0) return inferred;
    }
    return 0;
  }

  const originalBudget = resolveOriginalBudget();
  const originalTop1 = initData.original_top1 || null;

  // Bounds of the *change* (derived from the slider, itself derived from the
  // catalog price range on the server), so simulated_budget stays in range.
  const changeMin = slider ? parseInt(slider.min, 10) : -originalBudget;
  const changeMax = slider ? parseInt(slider.max, 10) : Number.MAX_SAFE_INTEGER;

  function formatInr(n) {
    return "₹" + Number(n).toLocaleString("en-IN");
  }

  function formatSignedInr(n) {
    const v = Number(n);
    if (v > 0) return "+" + formatInr(v);
    if (v < 0) return "−" + formatInr(Math.abs(v));
    return "₹0";
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }


  function clampChange(value) {
    let v = parseInt(value, 10);
    if (isNaN(v)) v = 0;
    if (v < changeMin) v = changeMin;
    if (v > changeMax) v = changeMax;
    return v;
  }

  // Keep slider and number input in sync and refresh the change / simulated
  // budget displays — WITHOUT triggering any recalculation.
  function syncControls(change, sourceEl) {
    const c = clampChange(change);
    if (slider && sourceEl !== slider) slider.value = c;
    if (input && sourceEl !== input) input.value = c === 0 ? "" : c;
    if (changeDisplay) changeDisplay.textContent = formatSignedInr(c);
    if (budgetDisplay) budgetDisplay.textContent = formatInr(originalBudget + c);
    return c;
  }

  // The active change: number input wins when non-empty, else the slider.
  function currentChange() {
    if (input && input.value !== "" && !isNaN(parseInt(input.value, 10))) {
      return clampChange(input.value);
    }
    return clampChange(slider ? slider.value : 0);
  }

  function renderLoading() {
    resultEl.innerHTML =
      '<div class="gm-sim-loading"><i class="bi bi-arrow-repeat gm-spin"></i> Recalculating your match…</div>';
  }

  function renderEmpty() {
    resultEl.innerHTML =
      '<div class="gm-sim-empty"><i class="bi bi-emoji-frown"></i> No phones match this budget. Try widening the range.</div>';
  }

  function renderError() {
    resultEl.innerHTML =
      '<div class="gm-sim-empty"><i class="bi bi-exclamation-triangle"></i> Couldn\u2019t update the simulation. Please try again.</div>';
  }

  function scoreBar(label, value) {
    const pct = Math.max(0, Math.min(100, Math.round(value * 10)));
    return `
      <div class="gm-score-bar-row">
        <span>${label}</span>
        <div class="gm-score-track"><div class="gm-score-fill" style="width:${pct}%"></div></div>
        <span class="gm-score-num">${value}</span>
      </div>`;
  }

  // A single simulated Top-3 card, styled like the original ranking cards.
  function simCard(phone) {
    return `
      <article class="gm-rank-card gm-rank-card--${phone.rank}">
        <div class="gm-rank-badge">#${phone.rank}${phone.rank === 1 ? " <span>Best Match</span>" : ""}</div>
        <div class="gm-rank-score">
          <svg viewBox="0 0 120 120" class="gm-ring-svg gm-ring-svg--result">
            <circle cx="60" cy="60" r="52" class="gm-ring-track"/>
            <circle cx="60" cy="60" r="52" class="gm-ring-fill" style="--pct: ${phone.match_score}"/>
          </svg>
          <div class="gm-ring-label"><span>${Math.round(phone.match_score)}</span><small>MATCH</small></div>
        </div>
        <h3 class="gm-rank-model">${escapeHtml(phone.model)}</h3>
        <div class="gm-rank-price">${formatInr(phone.price_inr)}</div>
        <div class="gm-rank-reason">${escapeHtml(phone.reason || "")}</div>
        <div class="gm-score-bars">
          ${scoreBar("📸 Camera", phone.camera_score)}
          ${scoreBar("⚡ Performance", phone.performance_score)}
          ${scoreBar("🔋 Battery", phone.battery_score)}
          ${scoreBar("💰 Value", phone.value_score)}
        </div>
      </article>`;
  }

  // Budget summary + Original #1 vs Simulated #1 + changed/unchanged reason.
  function summaryBlock(payload, change, simulatedBudget) {
    const origPick = originalTop1 || null;
    const simPick = payload.new_top1 || payload.phone || null;

    const origName = origPick ? escapeHtml(origPick.model) : "—";
    const simName = simPick ? escapeHtml(simPick.model) : "—";

    // "changed" is relative to the ORIGINAL recommendation, computed here so it
    // never depends on any cached/previous simulation.
    const changed = !(origPick && simPick && origPick.phone_id === simPick.phone_id);

    const budgetFacts = `
      <ul class="gm-sim-reasons" style="margin-top:0;">
        <li>Original budget: <strong>${formatInr(originalBudget)}</strong></li>
        <li>Budget change: <strong>${formatSignedInr(change)}</strong></li>
        <li>Simulated budget: <strong>${formatInr(simulatedBudget)}</strong></li>
        <li>Original #1 recommendation: <strong>${origName}</strong></li>
        <li>Simulated #1 recommendation: <strong>${simName}</strong></li>
      </ul>`;

    let explain;
    if (!changed) {
      explain = `
        <div class="gm-sim-same">
          <i class="bi bi-check-circle-fill"></i>
          <span>This is still the best recommendation even with the updated budget.</span>
        </div>`;
    } else {
      const priceDiff = payload.price_diff;
      let priceDiffLabel = "";
      if (typeof priceDiff === "number" && priceDiff !== 0) {
        priceDiffLabel = priceDiff > 0
          ? `${formatInr(Math.abs(priceDiff))} more than before`
          : `${formatInr(Math.abs(priceDiff))} less than before`;
      }
      const reasonsHtml = (payload.reasons || [])
        .map((r) => `<li>${escapeHtml(r)}</li>`)
        .join("");
      explain = `
        <div class="gm-sim-changed">
          <div class="gm-sim-changed-head"><i class="bi bi-arrow-repeat"></i> Why the recommendation changed</div>
          <div class="gm-sim-phone-row">
            <div class="gm-sim-phone-info">
              <div class="gm-sim-phone-name">${simName}</div>
              <div class="gm-sim-phone-price">
                ${simPick ? formatInr(simPick.price_inr) : ""}
                ${priceDiffLabel ? `<span class="gm-sim-price-diff">(${priceDiffLabel})</span>` : ""}
              </div>
            </div>
            ${simPick ? `<div class="gm-sim-match"><span>${Math.round(simPick.match_score)}</span><small>MATCH</small></div>` : ""}
          </div>
          ${reasonsHtml ? `<ul class="gm-sim-reasons">${reasonsHtml}</ul>` : ""}
        </div>`;
    }

    return `<div class="gm-sim-compare">${budgetFacts}${explain}</div>`;
  }

  function renderSimulated(payload, change, simulatedBudget) {
    if (!payload || !Array.isArray(payload.top3) || payload.top3.length === 0) {
      renderEmpty();
      return;
    }

    const cards = payload.top3.map(simCard).join("");

    resultEl.innerHTML = `
      <div class="gm-section-head gm-section-head--sm" style="margin-top:8px;">
        <span class="gm-eyebrow">What if?</span>
        <h2>Simulated Results</h2>
        <p class="gm-section-sub">Top 3 for a simulated budget of ${formatInr(simulatedBudget)} — same persona and priorities.</p>
      </div>
      <div class="gm-top3-grid">${cards}</div>
      ${summaryBlock(payload, change, simulatedBudget)}`;

  }

  function simulate() {
    const change = currentChange();
    syncControls(change); // reflect the clamped change everywhere before running
    // simulated_budget = original_budget + budget_change. Floor at the catalog
    // minimum so we always send a valid positive budget to the engine (a value
    // of 0 would make the engine skip budget filtering entirely).
    const catalogMin = Number(root.getAttribute("data-min-budget"));
    let simulatedBudget = originalBudget + change;
    if (Number.isFinite(catalogMin) && catalogMin > 0 && simulatedBudget < catalogMin) {
      simulatedBudget = catalogMin;
    }
    if (simulatedBudget < 1) simulatedBudget = 1;

    renderLoading();

    // Reuse the EXISTING recommendation API with the simulated budget. The
    // comparison baseline is always the ORIGINAL #1 pick (never cached from a
    // prior simulation), so the original recommendations stay authoritative.
    fetch("/api/simulate-budget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weights, budget: simulatedBudget, previous: originalTop1 }),
    })
      .then((res) => res.json())
      .then((payload) => renderSimulated(payload, change, simulatedBudget))
      .catch(renderError);
  }

  // Slider only updates the displayed change/budget (NO recalc while dragging).
  if (slider) {
    slider.addEventListener("input", () => {
      syncControls(slider.value, slider);
    });
  }

  // Number input also only updates the displayed values; it does not recalc.
  if (input) {
    input.addEventListener("input", () => {
      if (input.value === "") {
        syncControls(0, input);
        return;
      }
      syncControls(input.value, input);
    });
  }

  // Recalculation happens ONLY on the button click. Repeatable any number of
  // times; each run recomputes from the original budget + current change.
  if (updateBtn) {
    updateBtn.addEventListener("click", simulate);
  }
});