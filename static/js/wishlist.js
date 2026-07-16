/* wishlist.js - renders saved phones from localStorage */

document.addEventListener("DOMContentLoaded", () => {
  const storage = window.GalaxyMatchStorage;
  const content = document.getElementById("gm-wishlist-content");
  const dataEl = document.getElementById("all-wishlist-phones-data");

  if (!storage || !content || !dataEl) return;

  let phones = [];
  try {
    phones = JSON.parse(dataEl.textContent);
  } catch (_) {
    phones = [];
  }

  const catalogById = new Map(phones.map((phone) => [String(phone.phone_id), phone]));

  function phoneLookup(id) {
    const saved = storage.getWishlist().find((item) => String(item.phone_id) === String(id));
    return { ...(catalogById.get(String(id)) || {}), ...(saved || {}) };
  }

  function render() {
    const savedPhones = storage
      .getWishlist()
      .map((phone) => ({ ...(catalogById.get(String(phone.phone_id)) || {}), ...phone }))
      .filter((phone) => phone.phone_id != null);

    if (!savedPhones.length) {
      content.innerHTML = `
        <div class="gm-empty-state">
          <i class="bi bi-heart"></i>
          <h3>Your wishlist is empty</h3>
          <p>Tap the heart on any recommendation card to save it here.</p>
          <a href="${window.location.origin}/" class="btn gm-btn-primary">Find recommendations</a>
        </div>`;
      return;
    }

    content.innerHTML = `
      <div class="gm-top3-grid">
        ${savedPhones.map((phone) => storage.phoneCardHtml(phone, { showRemove: true })).join("")}
      </div>`;
    storage.syncWishlistButtons(content);
  }

  content.addEventListener("click", (event) => {
    const removeButton = event.target.closest(".gm-wishlist-remove");
    if (!removeButton) return;
    storage.removeWishlist(removeButton.dataset.phoneId);
    render();
  });

  storage.bindWishlistButtons(content, phoneLookup);
  window.addEventListener("gm:wishlist-updated", render);
  render();
});