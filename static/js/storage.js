/* storage.js - shared localStorage helpers for wishlist and recommendation history */

(function () {
  const WISHLIST_KEY = "gmWishlist";
  const HISTORY_KEY = "gmRecommendationHistory";

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) {}
  }

  function normalizeId(id) {
    return String(id);
  }

  function getWishlist() {
    return readJSON(WISHLIST_KEY, []);
  }

  function setWishlist(items) {
    writeJSON(WISHLIST_KEY, items);
    window.dispatchEvent(new CustomEvent("gm:wishlist-updated"));
  }

  function isWishlisted(id) {
    const phoneId = normalizeId(id);
    return getWishlist().some((item) => normalizeId(item.phone_id) === phoneId);
  }

  function addWishlist(phone) {
    if (!phone || phone.phone_id == null || isWishlisted(phone.phone_id)) return;
    setWishlist([...getWishlist(), phone]);
  }

  function removeWishlist(id) {
    const phoneId = normalizeId(id);
    setWishlist(getWishlist().filter((item) => normalizeId(item.phone_id) !== phoneId));
  }

  function toggleWishlist(phone) {
    if (!phone || phone.phone_id == null) return false;
    if (isWishlisted(phone.phone_id)) {
      removeWishlist(phone.phone_id);
      return false;
    }
    addWishlist(phone);
    return true;
  }

  function getHistory() {
    return readJSON(HISTORY_KEY, []);
  }

  function saveHistoryEntry(entry) {
    if (!entry || !Array.isArray(entry.top3) || !entry.top3.length) return;
    const history = getHistory();
    const signature = JSON.stringify({
      source_type: entry.source_type,
      source_label: entry.source_label,
      budget: entry.budget,
      weights: entry.weights,
      top3: entry.top3.map((phone) => ({
        phone_id: phone.phone_id,
        match_score: phone.match_score,
      })),
    });
    if (history[0]?.signature === signature) return;

    const timestamp = new Date().toISOString();
    const savedEntry = {
      ...entry,
      id: `${timestamp}-${Math.random().toString(36).slice(2, 8)}`,
      signature,
      timestamp,
    };
    writeJSON(HISTORY_KEY, [savedEntry, ...history]);
  }

  function clearHistory() {
    writeJSON(HISTORY_KEY, []);
  }

  function formatINR(value) {
    if (typeof gmFormatINR === "function") return gmFormatINR(value);
    return "Rs " + Number(value).toLocaleString("en-IN");
  }

  function formatDateTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function scoreBar(label, score) {
    const safeScore = Number(score || 0);
    return `
      <div class="gm-score-bar-row">
        <span>${label}</span>
        <div class="gm-score-track"><div class="gm-score-fill" style="width:${Math.round(safeScore * 10)}%"></div></div>
        <span class="gm-score-num">${safeScore}</span>
      </div>`;
  }

  function phoneCardHtml(phone, options = {}) {
    const rank = options.rank || phone.rank || "";
    const rankClass = rank ? ` gm-rank-card--${rank}` : "";
    const matchScore = phone.match_score != null ? Math.round(phone.match_score) : null;
    const reason = options.reason || phone.reason || "";
    const wishlistButton = options.showWishlist === false ? "" : `
      <button class="gm-wishlist-toggle" type="button" data-phone-id="${phone.phone_id}" aria-label="Toggle wishlist">
        <i class="bi bi-heart"></i>
      </button>`;
    const removeButton = options.showRemove ? `
      <button class="btn gm-btn-outline gm-wishlist-remove" type="button" data-phone-id="${phone.phone_id}">
        <i class="bi bi-heartbreak"></i> Remove
      </button>` : "";

    return `
      <article class="gm-rank-card${rankClass}">
        ${wishlistButton}
        ${rank ? `<div class="gm-rank-badge">#${rank}${rank === 1 ? " <span>Best Match</span>" : ""}</div>` : ""}
        ${matchScore != null ? `
        <div class="gm-rank-score">
          <svg viewBox="0 0 120 120" class="gm-ring-svg gm-ring-svg--result">
            <circle cx="60" cy="60" r="52" class="gm-ring-track"/>
            <circle cx="60" cy="60" r="52" class="gm-ring-fill" style="--pct: ${matchScore}"/>
          </svg>
          <div class="gm-ring-label"><span>${matchScore}</span><small>MATCH</small></div>
        </div>` : ""}
        <h3 class="gm-rank-model">${escapeHtml(phone.model)}</h3>
        <div class="gm-rank-price">${formatINR(phone.price_inr)}</div>
        ${reason ? `<div class="gm-rank-reason">${escapeHtml(reason)}</div>` : ""}
        <div class="gm-score-bars">
          ${scoreBar("Camera", phone.camera_score)}
          ${scoreBar("Performance", phone.performance_score)}
          ${scoreBar("Battery", phone.battery_score)}
          ${scoreBar("Display", phone.display_score)}
        </div>
        <ul class="gm-spec-list">
          <li><i class="bi bi-cpu"></i> ${escapeHtml(phone.processor)}</li>
          <li><i class="bi bi-memory"></i> ${phone.ram_gb}GB RAM · ${phone.storage_gb}GB</li>
          <li><i class="bi bi-battery-charging"></i> ${phone.battery_mah}mAh · ${phone.charging_w}W</li>
          <li><i class="bi bi-camera"></i> ${phone.main_camera_mp}MP main</li>
          <li><i class="bi bi-aspect-ratio"></i> ${escapeHtml(phone.display_inch)}" · ${phone.refresh_rate_hz}Hz</li>
        </ul>
        ${removeButton}
      </article>`;
  }

  function syncWishlistButtons(root = document) {
    root.querySelectorAll(".gm-wishlist-toggle").forEach((button) => {
      const active = isWishlisted(button.dataset.phoneId);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.innerHTML = `<i class="bi ${active ? "bi-heart-fill" : "bi-heart"}"></i>`;
    });
  }

  function bindWishlistButtons(root, phoneLookup) {
    root.addEventListener("click", (event) => {
      const button = event.target.closest(".gm-wishlist-toggle");
      if (!button) return;
      const phone = phoneLookup(button.dataset.phoneId);
      if (!phone) return;
      toggleWishlist(phone);
      syncWishlistButtons(document);
    });

    window.addEventListener("gm:wishlist-updated", () => syncWishlistButtons(document));
    syncWishlistButtons(root);
  }

  window.GalaxyMatchStorage = {
    getWishlist,
    addWishlist,
    removeWishlist,
    toggleWishlist,
    isWishlisted,
    getHistory,
    saveHistoryEntry,
    clearHistory,
    formatDateTime,
    escapeHtml,
    phoneCardHtml,
    bindWishlistButtons,
    syncWishlistButtons,
  };
})();