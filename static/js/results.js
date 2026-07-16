/* results.js — floating compare tray on the results page */

document.addEventListener("DOMContentLoaded", () => {
  const tray = document.getElementById("gm-compare-tray");
  const slotsWrap = document.getElementById("gm-compare-slots");
  const goBtn = document.getElementById("gm-compare-go");
  const addButtons = document.querySelectorAll(".gm-compare-add");
  const storage = window.GalaxyMatchStorage;
  const phonesDataEl = document.getElementById("all-results-phones-data");
  const historyDataEl = document.getElementById("recommendation-history-data");

  function parseJsonScript(el, fallback) {
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent);
    } catch (_) {
      return fallback;
    }
  }

  const phones = parseJsonScript(phonesDataEl, []);
  const phoneById = new Map(phones.map((phone) => [String(phone.phone_id), phone]));

  if (storage) {
    storage.bindWishlistButtons(document, (id) => phoneById.get(String(id)));
    storage.saveHistoryEntry(parseJsonScript(historyDataEl, null));
  }

  let selected = [null, null]; // {id, name}

  function renderSlots() {
    const slotEls = slotsWrap.querySelectorAll(".gm-compare-slot");
    selected.forEach((item, idx) => {
      const slotEl = slotEls[idx];
      if (item) {
        slotEl.classList.add("gm-slot-filled");
        slotEl.innerHTML = `<span>${item.name}</span> <i class="bi bi-x-circle-fill gm-slot-remove" data-idx="${idx}"></i>`;
      } else {
        slotEl.classList.remove("gm-slot-filled");
        slotEl.innerHTML = `<span>Add a phone</span>`;
      }
    });

    const trayShouldShow = selected.some((s) => s !== null);
    tray.classList.toggle("gm-tray-visible", trayShouldShow);

    goBtn.disabled = !(selected[0] && selected[1]);

  }

  function addToCompare(id, name) {
    // Already selected? no-op
    if (selected.some((s) => s && s.id === id)) return;

    // Fill first empty slot, or replace slot 0 if both full
    const emptyIdx = selected.findIndex((s) => s === null);
    if (emptyIdx !== -1) {
      selected[emptyIdx] = { id, name };
    } else {
      selected = [selected[1], { id, name }];
    }
    renderSlots();
  }

  addButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.phoneId;
      const name = btn.dataset.phoneName;
      addToCompare(id, name);
    });
  });

  slotsWrap.addEventListener("click", (e) => {
    if (e.target.classList.contains("gm-slot-remove")) {
      const idx = parseInt(e.target.dataset.idx, 10);
      selected[idx] = null;
      renderSlots();
    }
  });

  goBtn.addEventListener("click", () => {
    if (selected[0] && selected[1]) {
      window.location.href = `/compare?a=${selected[0].id}&b=${selected[1].id}`;
    }
  });

  renderSlots();
});