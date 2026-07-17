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

  // Only step across tiers that actually unlock a phone.
  var steps = tiers.filter(function (t) { return t && t.available; });
  if (!steps.length) return;

  var idx = 0; // start at the smallest available increment

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
    if (idx < steps.length - 1) { idx++; render(); }
  });
  if (el.minus) el.minus.addEventListener("click", function () {
    if (idx > 0) { idx--; render(); }
  });

  render();
})();