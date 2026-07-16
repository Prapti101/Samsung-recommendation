/* history.js - renders local recommendation history */

document.addEventListener("DOMContentLoaded", () => {
  const storage = window.GalaxyMatchStorage;
  const content = document.getElementById("gm-history-content");
  const detail = document.getElementById("gm-history-detail");
  const clearButton = document.getElementById("gm-history-clear");
  const phoneById = new Map();

  if (!storage || !content || !detail || !clearButton) return;

  function registerPhones(entry) {
    (entry.top3 || []).forEach((phone) => {
      phoneById.set(String(phone.phone_id), phone);
    });
  }

  function renderEmpty() {
    content.innerHTML = `
      <div class="gm-empty-state">
        <i class="bi bi-clock-history"></i>
        <h3>No recommendation history yet</h3>
        <p>Generate recommendations and they will appear here automatically.</p>
        <a href="${window.location.origin}/" class="btn gm-btn-primary">Get my matches</a>
      </div>`;
    detail.innerHTML = "";
    clearButton.disabled = true;
  }

  function renderDetail(entry) {
    registerPhones(entry);
    detail.innerHTML = `
      <div class="gm-section-head gm-section-head--sm gm-mt-lg">
        <span class="gm-eyebrow">Restored result</span>
        <h2>${storage.escapeHtml(entry.source_label)}</h2>
        <p class="gm-section-sub">${storage.formatDateTime(entry.timestamp)}</p>
      </div>
      <div class="gm-top3-grid">
        ${(entry.top3 || []).map((phone, index) => storage.phoneCardHtml(phone, {
          rank: index + 1,
          showWishlist: true,
        })).join("")}
      </div>`;
    storage.syncWishlistButtons(detail);
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderHistory() {
    const history = storage.getHistory();
    phoneById.clear();
    history.forEach(registerPhones);

    if (!history.length) {
      renderEmpty();
      return;
    }

    clearButton.disabled = false;
    content.innerHTML = `
      <div class="gm-history-list">
        ${history.map((entry) => {
          const topPhones = (entry.top3 || []).map((phone) => `${phone.model} (${Math.round(phone.match_score)}%)`).join(", ");
          return `
            <button class="gm-history-entry" type="button" data-entry-id="${entry.id}">
              <span class="gm-history-entry-date">${storage.formatDateTime(entry.timestamp)}</span>
              <span class="gm-history-entry-title">${storage.escapeHtml(entry.source_label)}</span>
              <span class="gm-history-entry-meta">${storage.escapeHtml(topPhones)}</span>
            </button>`;
        }).join("")}
      </div>`;
  }

  content.addEventListener("click", (event) => {
    const entryButton = event.target.closest(".gm-history-entry");
    if (!entryButton) return;
    const entry = storage.getHistory().find((item) => item.id === entryButton.dataset.entryId);
    if (!entry) return;
    content.querySelectorAll(".gm-history-entry").forEach((button) => button.classList.remove("active"));
    entryButton.classList.add("active");
    renderDetail(entry);
  });

  clearButton.addEventListener("click", () => {
    storage.clearHistory();
    renderHistory();
  });

  storage.bindWishlistButtons(detail, (id) => phoneById.get(String(id)));
  renderHistory();
});