/* home_entry.js — premium loading overlay for the recommendation entry.
 * -------------------------------------------------------------------
 * After the user submits any of the three entry methods (Default Personas,
 * Describe It, or the embedded Persona Quiz), we show a premium loading
 * overlay with rotating status messages for ~3.5s, THEN let the original
 * submission proceed to /recommend exactly as before.
 *
 * No recommendation logic is touched: for the home form we defer the native
 * submit; for the quiz (embedded via same-origin iframe) we intercept its
 * form submit, retarget it to the top window, and submit after the delay.
 */

(function () {
  "use strict";

  const MESSAGES = [
    "Analyzing your preferences...",
    "Matching your lifestyle with Galaxy devices...",
    "Scoring Galaxy devices...",
    "Finding your best match...",
    "Preparing personalized recommendations...",
  ];
  const HOLD_MS = 3500;       // total overlay time before navigating
  const ROTATE_MS = 1000;     // message change cadence

  const overlay = document.getElementById("gm-loading-overlay");
  const msgEl = document.getElementById("gm-loading-msg");
  if (!overlay || !msgEl) return;

  let rotateTimer = null;

  function showOverlay() {
    let i = 0;
    msgEl.textContent = MESSAGES[0];
    overlay.classList.add("is-visible");
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    rotateTimer = setInterval(() => {
      i = (i + 1) % MESSAGES.length;
      // fade out -> swap -> fade in
      msgEl.classList.add("is-fading");
      setTimeout(() => {
        msgEl.textContent = MESSAGES[i];
        msgEl.classList.remove("is-fading");
      }, 220);
    }, ROTATE_MS);
  }

  function stopRotation() {
    if (rotateTimer) clearInterval(rotateTimer);
  }

  /* ---------- 1. Home form (Personas + Describe It) ---------- */
  const homeForm = document.getElementById("gm-form");
  if (homeForm) {
    homeForm.addEventListener("submit", (e) => {
      // Defer the real submission until the overlay has played.
      e.preventDefault();
      showOverlay();
      setTimeout(() => {
        stopRotation();
        homeForm.submit();   // native submit -> /recommend (unchanged)
      }, HOLD_MS);
    });
  }

  /* ---------- 2. Embedded Persona Quiz (same-origin iframe) ---------- */
  const frame = document.getElementById("gm-quiz-frame");
  if (frame) {
    frame.addEventListener("load", () => {
      let doc;
      try {
        doc = frame.contentDocument || frame.contentWindow.document;
      } catch (_) {
        return; // cross-origin (shouldn't happen — same origin) -> leave quiz as-is
      }
      const quizForm = doc.getElementById("gm-quiz-form");
      if (!quizForm) return;

      // Make the quiz submit navigate the TOP window (break out of the iframe)
      // so results replace the whole page, and show our overlay first.
      quizForm.addEventListener("submit", (e) => {
        // The quiz's own handler (quiz.js) has already validated the last step
        // and filled the hidden weight/budget fields. If it prevented submit
        // (unanswered final step), the event won't reach navigation anyway.
        // We only act once the quiz allows submission to proceed.
        if (e.defaultPrevented) return;

        e.preventDefault();
        quizForm.setAttribute("target", "_top");   // navigate parent, not frame
        showOverlay();
        setTimeout(() => {
          stopRotation();
          quizForm.submit();   // native POST -> /recommend in the top window
        }, HOLD_MS);
      });
    });
  }
})();