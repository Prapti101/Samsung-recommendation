/* theme.js — Premium theme system (Light / Dark / Auto)
 * -----------------------------------------------------
 * Applies and persists the user's theme choice. The initial theme is set by a
 * tiny inline script in <head> (anti-flash); this file wires up the segmented
 * control, keeps the active state + sliding thumb in sync, and — in Auto mode —
 * follows the OS appearance live via prefers-color-scheme.
 *
 * Choices: "light" | "dark" | "auto". Stored in localStorage under "gmTheme".
 * The resolved theme ("light"/"dark") is written to <html data-theme>, which
 * drives every CSS variable. No other JS needs to know about theming.
 */

(function () {
  const KEY = "gmTheme";
  const DEFAULT = "light";
  const root = document.documentElement;
  const mql = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function getChoice() {
    try {
      const v = localStorage.getItem(KEY);
      if (v === "light" || v === "dark" || v === "auto") return v;
    } catch (_) {}
    return DEFAULT;
  }

  function setChoice(choice) {
    try { localStorage.setItem(KEY, choice); } catch (_) {}
  }

  function resolve(choice) {
    if (choice === "dark") return "dark";
    if (choice === "auto") return mql && mql.matches ? "dark" : "light";
    return "light";
  }

  function apply(choice) {
    const theme = resolve(choice);
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-theme-choice", choice);
  }

  function syncControl(choice) {
    const group = document.getElementById("gm-theme-switch");
    const thumb = document.getElementById("gm-theme-thumb");
    if (!group) return;
    const buttons = Array.from(group.querySelectorAll(".gm-theme-opt"));
    let activeIndex = 0;
    buttons.forEach((btn, i) => {
      const active = btn.dataset.themeValue === choice;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      if (active) activeIndex = i;
    });
    // Slide the thumb over the active segment (equal thirds).
    if (thumb && buttons.length) {
      thumb.style.transform = "translateX(" + (activeIndex * 100) + "%)";
    }
  }

  function init() {
    const group = document.getElementById("gm-theme-switch");
    if (!group) return;

    let choice = getChoice();
    apply(choice);
    syncControl(choice);

    group.addEventListener("click", (e) => {
      const btn = e.target.closest(".gm-theme-opt");
      if (!btn) return;
      choice = btn.dataset.themeValue;
      setChoice(choice);
      apply(choice);
      syncControl(choice);
    });

    // Auto mode: react to OS theme changes live (no refresh needed).
    if (mql) {
      const onChange = () => {
        if (getChoice() === "auto") {
          apply("auto");
          syncControl("auto");
        }
      };
      if (mql.addEventListener) mql.addEventListener("change", onChange);
      else if (mql.addListener) mql.addListener(onChange); // older Safari
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();