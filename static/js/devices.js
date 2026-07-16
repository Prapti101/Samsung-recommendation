/* devices.js — client-side filtering for the "View All" catalog.
 *
 * Presentation only: every phone is already rendered server-side, so this just
 * shows/hides cards. It does not score, rank or recommend anything, and it
 * never talks to the recommendation APIs.
 */

document.addEventListener("DOMContentLoaded", () => {
  const grid = document.getElementById("gm-cat-grid");
  if (!grid) return;

  const cards = Array.from(grid.querySelectorAll(".gm-cat-card"));
  const ramWrap = document.getElementById("gm-cat-ram");
  const priceInput = document.getElementById("gm-cat-price");
  const priceOut = document.getElementById("gm-cat-price-out");
  const wirelessInput = document.getElementById("gm-cat-wireless");
  const countOut = document.getElementById("gm-cat-count");
  const emptyState = document.getElementById("gm-cat-empty");
  const resetBtn = document.getElementById("gm-cat-reset");
  const emptyResetBtn = document.getElementById("gm-cat-empty-reset");

  const PRICE_MAX = Number(priceInput.max);
  const state = { ram: 0, maxPrice: PRICE_MAX, wireless: false };

  // Reuse the shared INR formatter when it's available (main.js), so prices on
  // this page read identically to the rest of the site.
  const formatINR = (value) =>
    typeof window.gmFormatINR === "function"
      ? window.gmFormatINR(value)
      : "₹" + Number(value).toLocaleString("en-IN");

  // Keep the wishlist hearts working exactly as they do elsewhere.
  const storage = window.GalaxyMatchStorage;
  if (storage && typeof storage.bindWishlistButtons === "function") {
    const byId = new Map();
    cards.forEach((card) => {
      const btn = card.querySelector(".gm-wishlist-toggle");
      if (!btn) return;
      byId.set(String(btn.dataset.phoneId), {
        phone_id: Number(btn.dataset.phoneId),
        model: card.querySelector(".gm-cat-name").textContent.trim(),
        price_inr: Number(card.dataset.price),
        image: (card.querySelector(".gm-cat-photo") || {}).src || null,
      });
    });
    storage.bindWishlistButtons(document, (id) => byId.get(String(id)));
  }

  function apply() {
    let shown = 0;

    cards.forEach((card) => {
      const matches =
        Number(card.dataset.ram) >= state.ram &&
        Number(card.dataset.price) <= state.maxPrice &&
        (!state.wireless || card.dataset.wireless === "1");

      card.classList.toggle("gm-hidden", !matches);
      if (matches) shown += 1;
    });

    countOut.textContent =
      shown === cards.length
        ? `${cards.length} phones`
        : `${shown} of ${cards.length} phones`;

    emptyState.classList.toggle("gm-hidden", shown !== 0);
    grid.classList.toggle("gm-hidden", shown === 0);
  }

  /* ---- Minimum RAM chips ---- */
  ramWrap.addEventListener("click", (e) => {
    const chip = e.target.closest(".gm-cat-chip");
    if (!chip) return;
    ramWrap.querySelectorAll(".gm-cat-chip").forEach((c) =>
      c.classList.toggle("is-active", c === chip)
    );
    state.ram = Number(chip.dataset.ram);
    apply();
  });

  /* ---- Max price ---- */
  priceInput.addEventListener("input", () => {
    state.maxPrice = Number(priceInput.value);
    priceOut.textContent = formatINR(state.maxPrice);
    apply();
  });

  /* ---- Wireless charging ---- */
  wirelessInput.addEventListener("change", () => {
    state.wireless = wirelessInput.checked;
    apply();
  });

  /* ---- Reset ---- */
  function reset() {
    state.ram = 0;
    state.maxPrice = PRICE_MAX;
    state.wireless = false;
    ramWrap.querySelectorAll(".gm-cat-chip").forEach((c) =>
      c.classList.toggle("is-active", c.dataset.ram === "0")
    );
    priceInput.value = PRICE_MAX;
    priceOut.textContent = formatINR(PRICE_MAX);
    wirelessInput.checked = false;
    apply();
  }
  if (resetBtn) resetBtn.addEventListener("click", reset);
  if (emptyResetBtn) emptyResetBtn.addEventListener("click", reset);

  apply();
});
