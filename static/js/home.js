/* home.js — homepage form interactions */

document.addEventListener("DOMContentLoaded", () => {

  /* ---------- Mode toggle: persona vs free text ---------- */
  const modeButtons = document.querySelectorAll(".gm-mode-btn");
  const panels = {
    persona: document.getElementById("panel-persona"),
    text: document.getElementById("panel-text"),
  };

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.mode;
      Object.entries(panels).forEach(([key, panel]) => {
        panel.classList.toggle("gm-hidden", key !== mode);
      });
      // When switching to text mode, clear persona selection requirement (and vice versa)
      if (mode === "text") {
        document.getElementById("user_text").focus();
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
    });
  });

  /* ---------- Live persona-match preview while typing free text ---------- */
  const userText = document.getElementById("user_text");
  const hintBox = document.getElementById("gm-text-hint");
  let debounceTimer = null;

  if (userText) {
    userText.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      const text = userText.value.trim();

      if (text.length < 8) {
        hintBox.classList.remove("gm-hint-active");
        hintBox.innerHTML = '<i class="bi bi-magic"></i> We\'ll detect your persona and budget automatically as you type.';
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
            hintBox.innerHTML = msg;
            if (window.GalaxyMatchI18n) window.GalaxyMatchI18n.translatePage(hintBox);
          })
          .catch(() => {});
      }, 400);
    });
  }
});