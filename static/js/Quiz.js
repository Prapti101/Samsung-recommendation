/* quiz.js — Smart Discovery Quiz
 * -------------------------------
 * Drives the multi-step conversational quiz. Each option button carries
 * data-cam / data-perf / data-batt / data-val weight deltas (and, on the
 * budget step, a data-budget). As the user answers, we accumulate those
 * deltas per step; on submit we write the summed weights + chosen budget into
 * the hidden form fields and POST to the EXISTING /recommend route, which
 * normalises the four weights exactly like the home page's priority sliders.
 *
 * No recommendations are computed here — this only translates answers into
 * the four WSM weights + a budget. Personas remain a separate path.
 */

document.addEventListener("DOMContentLoaded", () => {
  const quiz = document.getElementById("gm-quiz");
  if (!quiz) return;

  const form = document.getElementById("gm-quiz-form");
  const slides = Array.from(quiz.querySelectorAll(".gm-quiz-slide"));
  const total = slides.length;

  const bar = document.getElementById("gm-quiz-bar");
  const stepNow = document.getElementById("gm-quiz-step-now");
  const stepTotal = document.getElementById("gm-quiz-step-total");

  const prevBtn = document.getElementById("gm-quiz-prev");
  const nextBtn = document.getElementById("gm-quiz-next");
  const finishBtn = document.getElementById("gm-quiz-finish");

  const budgetField = document.getElementById("gm-quiz-budget");
  const wFields = {
    camera: document.getElementById("gm-quiz-w-camera"),
    performance: document.getElementById("gm-quiz-w-performance"),
    battery: document.getElementById("gm-quiz-w-battery"),
    value: document.getElementById("gm-quiz-w-value"),
  };

  // Per-step recorded answer: { cam, perf, batt, val, budget? }. Keyed by
  // step index so re-answering a step replaces (not stacks) its contribution.
  const answers = new Array(total).fill(null);

  let current = 0;
  if (stepTotal) stepTotal.textContent = String(total);

  /* ---------- Progress + nav state ---------- */
  function updateChrome() {
    const pct = Math.round(((current + 1) / total) * 100);
    if (bar) bar.style.width = pct + "%";
    if (stepNow) stepNow.textContent = String(current + 1);

    prevBtn.disabled = current === 0;

    const answered = answers[current] != null;
    const isLast = current === total - 1;

    // Next vs Finish visibility
    nextBtn.classList.toggle("gm-hidden", isLast);
    finishBtn.classList.toggle("gm-hidden", !isLast);

    if (isLast) {
      finishBtn.disabled = !answered;
    } else {
      nextBtn.disabled = !answered;
    }
  }

  /* ---------- Slide transitions ---------- */
  function goTo(index, direction) {
    if (index < 0 || index >= total) return;
    const outgoing = slides[current];
    const incoming = slides[index];
    if (outgoing === incoming) {
      updateChrome();
      return;
    }

    outgoing.classList.remove("is-active");
    outgoing.classList.add(direction === "back" ? "is-leaving-back" : "is-leaving");

    // Clean up leaving state after the transition so it can re-enter later.
    const cleanup = () => {
      outgoing.classList.remove("is-leaving", "is-leaving-back");
      outgoing.removeEventListener("transitionend", cleanup);
    };
    outgoing.addEventListener("transitionend", cleanup);
    // Fallback in case transitionend doesn't fire (reduced motion, etc.)
    setTimeout(cleanup, 400);

    incoming.classList.remove("is-leaving", "is-leaving-back");
    incoming.classList.add(direction === "back" ? "is-entering-back" : "is-entering");
    // Force reflow so the entering transition plays.
    void incoming.offsetWidth;
    incoming.classList.add("is-active");
    incoming.classList.remove("is-entering", "is-entering-back");

    current = index;
    updateChrome();
    // Keep the active question in view on small screens.
    quiz.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ---------- Option selection ---------- */
  function recordSelection(slide, option) {
    const stepIndex = slides.indexOf(slide);
    if (stepIndex === -1) return;

    slide.querySelectorAll(".gm-quiz-option").forEach((btn) => {
      btn.classList.toggle("is-selected", btn === option);
      btn.setAttribute("aria-pressed", btn === option ? "true" : "false");
    });

    const num = (v) => {
      const n = parseFloat(v);
      return Number.isFinite(n) ? n : 0;
    };

    answers[stepIndex] = {
      cam: num(option.dataset.cam),
      perf: num(option.dataset.perf),
      batt: num(option.dataset.batt),
      val: num(option.dataset.val),
      budget: option.dataset.budget != null ? num(option.dataset.budget) : null,
    };

    updateChrome();

    // Gentle auto-advance for a smooth, app-like flow (not on the last step,
    // so the user can review before revealing results).
    if (stepIndex === current && current < total - 1) {
      window.setTimeout(() => {
        if (current === stepIndex) goTo(current + 1, "forward");
      }, 260);
    }
  }

  slides.forEach((slide) => {
    slide.querySelectorAll(".gm-quiz-option").forEach((option) => {
      option.addEventListener("click", () => recordSelection(slide, option));
    });
  });

  /* ---------- Nav buttons ---------- */
  prevBtn.addEventListener("click", () => goTo(current - 1, "back"));
  nextBtn.addEventListener("click", () => {
    if (answers[current] != null) goTo(current + 1, "forward");
  });

  /* ---------- Compose weights + budget on submit ---------- */
  function composeAndFill() {
    const totals = { camera: 0, performance: 0, battery: 0, value: 0 };
    let budget = null;

    answers.forEach((a) => {
      if (!a) return;
      totals.camera += a.cam;
      totals.performance += a.perf;
      totals.battery += a.batt;
      totals.value += a.val;
      if (a.budget != null) budget = a.budget;
    });

    // Guard: if somehow everything is zero, fall back to a balanced profile so
    // the recommender never receives an all-zero weight set.
    const sum = totals.camera + totals.performance + totals.battery + totals.value;
    if (sum <= 0) {
      totals.camera = totals.performance = totals.battery = totals.value = 25;
    }

    // The /recommend route re-normalises these to sum to 1.0, so raw sums are
    // fine to submit. Round to keep the payload tidy.
    wFields.camera.value = Math.round(totals.camera);
    wFields.performance.value = Math.round(totals.performance);
    wFields.battery.value = Math.round(totals.battery);
    wFields.value.value = Math.round(totals.value);

    if (budget != null) budgetField.value = String(Math.round(budget));
  }

  form.addEventListener("submit", (e) => {
    // Require the last step to be answered before revealing results.
    if (answers[total - 1] == null) {
      e.preventDefault();
      goTo(total - 1, "forward");
      return;
    }
    composeAndFill();
    // Let the native POST proceed to /recommend.
  });

  /* ---------- Init ---------- */
  updateChrome();
});