/* smart_upgrade.js — interactive "Smarter Upgrade" stepper.
 * ---------------------------------------------------------
 * Presentation only. Reads the pre-computed upgrade tiers (best phone the user
 * unlocks at +₹2,000 … +₹10,000) emitted by the server as JSON, and lets the
 * user step the extra budget up/down. Each step swaps the "Recommended upgrade"
 * card: real phone image, name, price, match %, five specs, and an
 * "Explore phone" link to samsung.com. No recommendation logic runs here.
 */
(function () {
  "use strict";

  var dataEl = document.getElementById("gm-upgrade-data");
  var section = document.getElementById("gm-smart-upgrade");
  if (!dataEl || !section) return;

  var tiers;
  try {
    tiers = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }
  if (!Array.isArray(tiers) || !tiers.length) return;

  // Walk EVERY increment, including the ones that unlock nothing — those now
  // say so rather than being skipped, so the ladder answers the whole question
  // ("what does +₹2,000 buy me?" -> "nothing better") instead of silently
  // jumping over it.
  var steps = tiers.filter(Boolean);
  if (!steps.length) return;

  // Open on the first increment that actually unlocks a phone, so the section
  // leads with a real upgrade (and matches what the server rendered).
  var idx = steps.findIndex(function (t) { return t.available; });
  if (idx < 0) idx = 0;

  var el = {
    plus:     document.getElementById("gm-step-plus"),
    minus:    document.getElementById("gm-step-minus"),
    amount:   document.getElementById("gm-step-amount"),
    photo:    document.getElementById("gm-up-photo"),
    name:     document.getElementById("gm-up-name"),
    name2:    document.getElementById("gm-up-name2"),
    price:    document.getElementById("gm-up-price"),
    match:    document.getElementById("gm-up-match"),
    delta:    document.getElementById("gm-up-delta"),
    features: document.getElementById("gm-up-features"),
    explore:  document.getElementById("gm-up-explore"),
    better:   document.getElementById("gm-upgrade-better")
  };

  function inr(n) {
    // Indian grouping, e.g. 134999 -> "1,34,999"
    var s = String(n), last3 = s.slice(-3), rest = s.slice(0, -3);
    if (rest) last3 = "," + last3;
    return rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + last3;
  }

  var ICONS = {
    camera:  "bi-camera-fill",
    cpu:     "bi-cpu-fill",
    battery: "bi-battery-charging",
    display: "bi-phone-fill",
    memory:  "bi-sd-card-fill"
  };

  function render() {
    var t = steps[idx];
    var p = t.pick;

    el.amount.textContent = "+₹" + inr(t.delta);
    if (el.delta) el.delta.textContent = "+₹" + inr(t.delta);

    // Fade the card while swapping content.
    if (el.better) {
      el.better.classList.remove("gm-upgrade-swap");
      void el.better.offsetWidth;
      el.better.classList.add("gm-upgrade-swap");
    }

    // This increment buys nothing better — say so plainly instead of leaving
    // the previous phone on screen next to a price it doesn't cost.
    if (!t.available || !p) {
      if (el.photo)  el.photo.style.display = "none";
      if (el.name)   el.name.textContent = "No better upgrade";
      if (el.name2)  el.name2.textContent = "";
      if (el.price)  el.price.textContent = "";
      if (el.match)  el.match.textContent = "";
      if (el.features) {
        el.features.innerHTML = '<li><i class="bi bi-info-circle"></i> ' +
          (t.message || "Nothing better for this increase.") + "</li>";
      }
      if (el.explore) el.explore.style.display = "none";
      if (el.minus) el.minus.disabled = (idx === 0);
      if (el.plus)  el.plus.disabled = (idx === steps.length - 1);
      return;
    }
    if (el.explore) el.explore.style.display = "";

    if (el.photo) {
      el.photo.src = p.image || "";
      el.photo.alt = p.model;
      el.photo.style.display = p.image ? "" : "none";
    }
    if (el.name)  el.name.textContent = p.model;
    if (el.name2) el.name2.textContent = p.model;
    if (el.price) el.price.textContent = "₹" + inr(p.price_inr);
    if (el.match) el.match.textContent = Math.round(p.match_score) + "%";

    // Five headline specs of the recommended phone.
    if (el.features) {
      el.features.innerHTML = (t.features || []).map(function (f) {
        var ic = ICONS[f.icon] || "bi-check-circle-fill";
        return '<li><i class="bi ' + ic + '"></i> ' + f.label + "</li>";
      }).join("");
    }

    if (el.explore) el.explore.href = t.explore_url || "#";

    // Enable/disable the steppers at the ends.
    if (el.minus) el.minus.disabled = (idx === 0);
    if (el.plus)  el.plus.disabled = (idx === steps.length - 1);
  }

  if (el.plus) el.plus.addEventListener("click", function () {
    stopAuto();                                   // manual click takes over
    if (idx < steps.length - 1) { idx++; render(); }
  });
  if (el.minus) el.minus.addEventListener("click", function () {
    stopAuto();
    if (idx > 0) { idx--; render(); }
  });

  /* ---------- Auto-advance ----------
     The stepper walks the upgrade ladder on its own so the section tells its
     story without the visitor discovering the +/- buttons. It bounces up the
     tiers and back down rather than snapping to the start, so the price only
     ever moves one step at a time.

     It stops for good the moment someone clicks + or -, pauses while the
     pointer is over the section (so nothing moves while you are reading it),
     and pauses when the tab is hidden. With only one tier there is nothing to
     cycle, so it never starts. */
  var AUTO_MS = 2600;
  var timer = null;
  var direction = 1;
  var manual = false;                             // set once the visitor clicks

  function tick() {
    if (steps.length < 2) return;
    if (idx + direction > steps.length - 1 || idx + direction < 0) {
      direction = -direction;                     // bounce at either end
    }
    idx += direction;
    render();
  }

  function startAuto() {
    if (timer || steps.length < 2) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    timer = setInterval(tick, AUTO_MS);
  }
  function stopAuto() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  if (section) {
    section.addEventListener("mouseenter", stopAuto);
    section.addEventListener("mouseleave", function () {
      // Only resume if the visitor never took manual control.
      if (!manual) startAuto();
    });
  }
  [el.plus, el.minus].forEach(function (b) {
    if (b) b.addEventListener("click", function () { manual = true; });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopAuto();
    else if (!manual) startAuto();
  });

  render();
  startAuto();
})();