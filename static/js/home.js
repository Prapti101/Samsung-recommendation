/* home.js — homepage form interactions */

document.addEventListener("DOMContentLoaded", () => {

  /* ---------- Mode toggle: persona / text / quiz ---------- */
  const modeButtons = document.querySelectorAll(".gm-mode-btn");
  const panels = {
    persona: document.getElementById("panel-persona"),
    text: document.getElementById("panel-text"),
    quiz: document.getElementById("panel-quiz"),
  };
  const tuneBlock = document.getElementById("gm-entry-tune");
  const submitRow = document.getElementById("gm-entry-submit");

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeButtons.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      const mode = btn.dataset.mode;

      Object.entries(panels).forEach(([key, panel]) => {
        if (panel) panel.classList.toggle("gm-hidden", key !== mode);
      });

      // The quiz is fully self-contained (it has its own budget + submit),
      // so hide the shared budget/priorities tuning and the main submit button
      // when quiz mode is active; show them for persona/text.
      const isQuiz = mode === "quiz";
      if (tuneBlock) tuneBlock.classList.toggle("gm-hidden", isQuiz);
      if (submitRow) submitRow.classList.toggle("gm-hidden", isQuiz);

      if (mode === "text") {
        const ut = document.getElementById("user_text");
        if (ut) ut.focus();
      }
    });
  });

  /* ---------- Budget slider ---------- */
  const budgetSlider = document.getElementById("budget");
  const budgetDisplay = document.getElementById("budget-display");
  if (budgetSlider) {
    const updateBudgetDisplay = () => {
      budgetDisplay.textContent = gmFormatINR(budgetSlider.value);
    };
    budgetSlider.addEventListener("input", updateBudgetDisplay);
    updateBudgetDisplay();
  }

  /* ---------- Priority sliders ----------
     Two bugs lived here:
       1. The sliders were hardcoded to 25% each in the HTML and nothing ever
          synced them to the chosen persona, so picking "Student" still showed
          25/25/25/25 while the engine actually ranked on 15/20/35/30. The
          sliders looked static and disagreed with the "Weights used" line on
          the results page.
       2. The label printed the slider's raw 0-100 value with a "%" sign, but
          four raw values don't sum to 100 — the backend normalises them. So the
          panel promised "auto-balance to 100%" and then didn't.
     Both are fixed by driving the sliders from the persona's real weights and
     labelling each one with its NORMALISED share, which is exactly what
     recommender.normalize_weights() computes server-side. */
  const priorityRows = Array.from(document.querySelectorAll(".gm-priority-row"));
  const touchedField = document.getElementById("gm-priorities-touched");

  function priorityInputs() {
    return priorityRows.map((row) => ({
      row,
      slider: row.querySelector("input[type=range]"),
      label: row.querySelector(".gm-priority-val"),
    }));
  }

  // Render each slider's share of the total — mirrors the backend's
  // weight / Σweights, so what the user sees is what the engine uses.
  function renderPriorityLabels() {
    const inputs = priorityInputs();
    const total = inputs.reduce((sum, i) => sum + Number(i.slider.value), 0);
    inputs.forEach((i) => {
      const share = total > 0 ? (Number(i.slider.value) / total) * 100 : 100 / inputs.length;
      i.label.textContent = Math.round(share) + "%";
    });
  }

  // Show the selected persona's actual weighting on the sliders.
  function syncSlidersToPersona(weights) {
    if (!weights) return;
    priorityInputs().forEach((i) => {
      const key = i.row.dataset.key;                 // camera | performance | battery | display
      if (weights[key] === undefined) return;
      i.slider.value = Math.round(weights[key] * 100);
    });
    renderPriorityLabels();
  }

  function selectedPersonaWeights() {
    const checked = document.querySelector('input[name="persona_id"]:checked');
    if (!checked || !checked.dataset.weights) return null;
    try {
      return JSON.parse(checked.dataset.weights);
    } catch (_) {
      return null;
    }
  }

  priorityInputs().forEach(({ slider }) => {
    slider.addEventListener("input", () => {
      // The user has overridden the persona, so the backend must use these
      // sliders rather than the persona's defaults.
      if (touchedField) touchedField.value = "1";
      renderPriorityLabels();
    });
  });

  // Switching persona re-points the sliders at that persona's weighting —
  // unless the user has already dragged one, in which case their override wins.
  document.querySelectorAll('input[name="persona_id"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      if (touchedField && touchedField.value === "1") return;
      syncSlidersToPersona(selectedPersonaWeights());
    });
  });

  // Open on the default persona's real weighting rather than a flat 25% each.
  syncSlidersToPersona(selectedPersonaWeights());
  renderPriorityLabels();

  /* ---------- Live persona-match preview while typing free text ---------- */
  const userText = document.getElementById("user_text");
  const hintBox = document.getElementById("gm-text-hint");
  let debounceTimer = null;

  /* ---------- Enter submits the description ----------
     The submit button sits below the budget/priority blocks, so describing a
     phone and pressing Enter felt like nothing happened. Enter now runs the
     recommendation straight away; Shift+Enter (and Ctrl/Cmd+Enter) still insert
     a newline for anyone writing a longer description. The Enter chip in the
     hint does the same thing on click. */
  const runDescribe = () => {
    if (!userText || !userText.value.trim()) return;   // nothing described yet
    const form = document.getElementById("gm-form");
    if (!form) return;
    // requestSubmit so the form's own submit handlers (loading overlay) run,
    // exactly as if the "Recommend my Top 3" button had been clicked.
    if (form.requestSubmit) form.requestSubmit();
    else form.submit();
  };

  if (userText) {
    userText.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      runDescribe();
    });
  }

  // Delegated: the hint's innerHTML is rewritten on every keystroke, so the
  // chip is a new element each time and can't hold its own listener.
  if (hintBox) {
    hintBox.addEventListener("click", (e) => {
      if (e.target.closest("#gm-enter-key")) runDescribe();
    });
  }

  // Markup for the clickable Enter chip, rebuilt whenever the hint re-renders.
  const ENTER_KEY_HTML = ' <button type="button" class="gm-kbd" id="gm-enter-key">Enter</button>';

  if (userText) {
    userText.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      const text = userText.value.trim();

      if (text.length < 8) {
        hintBox.classList.remove("gm-hint-active");
        hintBox.innerHTML = '<i class="bi bi-magic"></i> We\'ll detect your persona and budget automatically as you type' + ENTER_KEY_HTML;
        return;
      }

      debounceTimer = setTimeout(() => {
        fetch("/api/persona-match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        })
          .then((res) => res.json())
          .then((data) => {
            if (!data.matched) return;
            hintBox.classList.add("gm-hint-active");

            // The description asks for something we don't stock (an iPhone, a
            // laptop). Warn here rather than letting them press Enter and land
            // on a refusal page.
            if (data.supported === false) {
              hintBox.innerHTML =
                '<i class="bi bi-exclamation-circle"></i> ' + data.refusal;
              return;
            }

            let msg = `<i class="bi bi-magic"></i> ${data.emoji} <strong>${data.persona_name}</strong>`;
            if (data.budget) {
              msg += ` &middot; Budget: <strong>${gmFormatINR(data.budget)}</strong>`;
            }
            hintBox.innerHTML = msg + ENTER_KEY_HTML;
          })
          .catch(() => {});
      }, 400);
    });
  }
});