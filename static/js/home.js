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

  /* ---------- Priority sliders (auto-balance display %) ---------- */
  const priorityRows = document.querySelectorAll(".gm-priority-row");
  priorityRows.forEach((row) => {
    const slider = row.querySelector("input[type=range]");
    const valueLabel = row.querySelector(".gm-priority-val");
    slider.addEventListener("input", () => {
      valueLabel.textContent = slider.value + "%";
      // Mark that the user has customised priorities so the backend uses these
      // sliders instead of the persona's default weighting.
      const touched = document.getElementById("gm-priorities-touched");
      if (touched) touched.value = "1";
    });
  });

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
            let msg = `<i class="bi bi-magic"></i> Detected profile: ${data.emoji} <strong>${data.persona_name}</strong>`;
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