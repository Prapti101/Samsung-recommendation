/* compare.js — dynamic side-by-side comparison, no page reload needed */

document.addEventListener("DOMContentLoaded", () => {
  const dataEl = document.getElementById("all-phones-data");
  const phones = JSON.parse(dataEl.textContent);

  const pickerA = document.getElementById("picker-a");
  const pickerB = document.getElementById("picker-b");
  const resultWrap = document.getElementById("gm-compare-result");

  function findPhone(id) {
    return phones.find((p) => String(p.phone_id) === String(id));
  }

  const SCORE_ROWS = [
    { key: "camera_score", label: "Camera", icon: "📸" },
    { key: "performance_score", label: "Performance", icon: "⚡" },
    { key: "battery_score", label: "Battery", icon: "🔋" },
    { key: "display_score", label: "Display", icon: "🖥️" },
  ];

  function scoreRowHtml(a, b, row) {
    const va = a[row.key];
    const vb = b[row.key];
    const aWin = va >= vb ? "gm-win" : "";
    const bWin = vb >= va ? "gm-win" : "";
    const aWidth = Math.round(va * 5); // 0-10 -> 0-50% each side
    const bWidth = Math.round(vb * 5);
    return `
      <div class="gm-compare-score-row">
        <span class="gm-compare-score-num ${aWin}">${va}</span>
        <div class="gm-compare-score-mid">
          <span>${row.icon} ${row.label}</span>
          <div class="gm-compare-dualbar">
            <div class="gm-compare-dualbar-fill gm-compare-dualbar-fill--a" style="width:${aWidth}%"></div>
            <div class="gm-compare-dualbar-fill gm-compare-dualbar-fill--b" style="width:${bWidth}%"></div>
          </div>
        </div>
        <span class="gm-compare-score-num ${bWin}">${vb}</span>
      </div>`;
  }

  function specRow(label, a, b) {
    return `<tr><td class="gm-spec-label">${label}</td><td>${a}</td><td>${b}</td></tr>`;
  }

  function render(a, b) {
    if (!a || !b) {
      resultWrap.innerHTML = `
        <div class="gm-empty-state">
          <i class="bi bi-arrow-left-right"></i>
          <h3>Choose two phones to compare</h3>
          <p>Pick any two Galaxy models above and we'll break down every spec and score.</p>
        </div>`;
      return;
    }

    const scoresHtml = SCORE_ROWS.map((row) => scoreRowHtml(a, b, row)).join("");

    resultWrap.innerHTML = `
      <div class="gm-compare-card-heads">
        <div class="gm-compare-head"><h3>${a.model}</h3><div class="gm-compare-price">${gmFormatINR(a.price_inr)}</div></div>
        <div class="gm-compare-head gm-compare-head--vs">vs</div>
        <div class="gm-compare-head"><h3>${b.model}</h3><div class="gm-compare-price">${gmFormatINR(b.price_inr)}</div></div>
      </div>
      <div class="gm-compare-scores">${scoresHtml}</div>
      <div class="gm-table-wrap">
        <table class="gm-table gm-table--compare">
          <tbody>
            ${specRow("Processor", a.processor, b.processor)}
            ${specRow("RAM / Storage", `${a.ram_gb}GB / ${a.storage_gb}GB`, `${b.ram_gb}GB / ${b.storage_gb}GB`)}
            ${specRow("Battery", `${a.battery_mah}mAh · ${a.charging_w}W`, `${b.battery_mah}mAh · ${b.charging_w}W`)}
            ${specRow("Main Camera", `${a.main_camera_mp}MP`, `${b.main_camera_mp}MP`)}
            ${specRow("Ultra-wide", `${a.ultra_wide_mp}MP`, `${b.ultra_wide_mp}MP`)}
            ${specRow("Telephoto", a.telephoto_mp > 0 ? `${a.telephoto_mp}MP` : "—", b.telephoto_mp > 0 ? `${b.telephoto_mp}MP` : "—")}
            ${specRow("Front Camera", `${a.front_camera_mp}MP`, `${b.front_camera_mp}MP`)}
            ${specRow("Display", `${a.display_inch}" · ${a.refresh_rate_hz}Hz`, `${b.display_inch}" · ${b.refresh_rate_hz}Hz`)}
            ${specRow("Display Type", a.display_type, b.display_type)}
            ${specRow("Weight", `${a.weight_g}g`, `${b.weight_g}g`)}
            ${specRow("Category", a.category, b.category)}
          </tbody>
        </table>
      </div>`;

  }

  function handleChange() {
    const a = findPhone(pickerA.value);
    const b = findPhone(pickerB.value);
    render(a, b);

    // Keep the URL shareable/bookmarkable without a full reload
    const params = new URLSearchParams();
    if (pickerA.value) params.set("a", pickerA.value);
    if (pickerB.value) params.set("b", pickerB.value);
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, "", newUrl);
  }

  pickerA.addEventListener("change", handleChange);
  pickerB.addEventListener("change", handleChange);
});