/* insights.js — Recommendation Insights radar chart
 * --------------------------------------------------
 * Visualises the five strength dimensions of each Top-3 recommendation using a
 * lightweight, dependency-free SVG radar chart. All values are read directly
 * from the recommendation data already produced by the backend (camera /
 * performance / battery / value scores from the WSM engine, plus the
 * ai_longevity_score computed server-side). Nothing is recalculated here and
 * no scores are hardcoded — this file only draws what the backend provides.
 */

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("gm-insights");
  if (!root) return;

  const svg = document.getElementById("gm-radar-svg");
  const tabsWrap = document.getElementById("gm-insights-tabs");
  const legend = document.getElementById("gm-insights-legend");
  const tooltip = document.getElementById("gm-radar-tooltip");
  const dataEl = document.getElementById("gm-insights-data");
  if (!svg || !dataEl) return;

  let phones = [];
  try {
    phones = JSON.parse(dataEl.textContent) || [];
  } catch (_) {
    phones = [];
  }
  if (!phones.length) {
    root.style.display = "none";
    return;
  }

  const SVGNS = "http://www.w3.org/2000/svg";

  // Five radar dimensions. `key` maps to the backend field; `explain` is the
  // short description shown on hover. All scores are on a 0-10 scale.
  const DIMENSIONS = [
    { key: "camera_score", label: "Camera", icon: "📸",
      explain: "How strong the cameras are for photos & video." },
    { key: "performance_score", label: "Performance", icon: "⚡",
      explain: "Chipset speed, RAM and smoothness for apps & games." },
    { key: "battery_score", label: "Battery", icon: "🔋",
      explain: "Battery capacity and charging speed for all-day use." },
    { key: "value_score", label: "Value", icon: "💰",
      explain: "How much phone you get for the price." },
    { key: "ai_longevity_score", label: "AI & Longevity", icon: "🤖",
      explain: "Galaxy AI readiness plus how future-proof it stays over time." },
  ];

  const SIZE = 320;
  const CENTER = SIZE / 2;
  const RADIUS = 108;          // outer ring radius
  const RINGS = 4;             // gridline rings (each = 2.5 points)
  const MAX = 10;
  const N = DIMENSIONS.length;

  let currentIndex = 0;

  /* ---- geometry helpers ---- */
  function angleFor(i) {
    // Start at top (-90°), go clockwise.
    return (-Math.PI / 2) + (i * 2 * Math.PI / N);
  }
  function pointFor(i, value) {
    const r = (value / MAX) * RADIUS;
    const a = angleFor(i);
    return [CENTER + r * Math.cos(a), CENTER + r * Math.sin(a)];
  }
  function polygonPoints(values) {
    return values.map((v, i) => pointFor(i, v).join(",")).join(" ");
  }
  function el(tag, attrs) {
    const node = document.createElementNS(SVGNS, tag);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    return node;
  }

  /* ---- static scaffold (rings, spokes, axis labels) ---- */
  function drawScaffold() {
    // Gridline rings
    for (let ring = 1; ring <= RINGS; ring++) {
      const rr = (ring / RINGS) * RADIUS;
      const pts = DIMENSIONS.map((_, i) => {
        const a = angleFor(i);
        return [CENTER + rr * Math.cos(a), CENTER + rr * Math.sin(a)].join(",");
      }).join(" ");
      svg.appendChild(el("polygon", {
        points: pts,
        class: "gm-radar-ring",
      }));
    }

    // Spokes + axis labels
    DIMENSIONS.forEach((dim, i) => {
      const [x, y] = pointFor(i, MAX);
      svg.appendChild(el("line", {
        x1: CENTER, y1: CENTER, x2: x, y2: y, class: "gm-radar-spoke",
      }));

      // Label just outside the outer ring
      const la = angleFor(i);
      const lx = CENTER + (RADIUS + 26) * Math.cos(la);
      const ly = CENTER + (RADIUS + 26) * Math.sin(la);
      const label = el("text", {
        x: lx, y: ly, class: "gm-radar-axis-label",
        "text-anchor": "middle", "dominant-baseline": "middle",
      });
      label.textContent = dim.icon + " " + dim.label;
      svg.appendChild(label);
    });
  }

  /* ---- data polygon + points (animated) ---- */
  let dataPolygon = null;
  let dataDots = [];

  function valuesFor(phone) {
    return DIMENSIONS.map((d) => {
      const v = Number(phone[d.key]);
      return Number.isFinite(v) ? Math.max(0, Math.min(MAX, v)) : 0;
    });
  }

  function drawData(values, animate) {
    // Filled polygon
    if (!dataPolygon) {
      dataPolygon = el("polygon", { class: "gm-radar-area", points: polygonPoints(values) });
      svg.appendChild(dataPolygon);
    } else {
      // CSS transition handles the smooth morph between point sets.
      dataPolygon.setAttribute("points", polygonPoints(values));
    }

    // Vertex dots (hover targets)
    if (!dataDots.length) {
      DIMENSIONS.forEach((dim, i) => {
        const [x, y] = pointFor(i, values[i]);
        const dot = el("circle", { cx: x, cy: y, r: 5, class: "gm-radar-dot", "data-dim": i });
        svg.appendChild(dot);
        bindDotHover(dot, i);
        dataDots.push(dot);
      });
    } else {
      dataDots.forEach((dot, i) => {
        const [x, y] = pointFor(i, values[i]);
        dot.setAttribute("cx", x);
        dot.setAttribute("cy", y);
      });
    }

    if (!animate) {
      // No transition on first paint.
      dataPolygon.style.transition = "none";
      // Force reflow, then restore transitions for later updates.
      void dataPolygon.getBBox();
      requestAnimationFrame(() => {
        dataPolygon.style.transition = "";
      });
    }
  }

  /* ---- tooltip ---- */
  function showTooltip(i, x, y) {
    const dim = DIMENSIONS[i];
    const phone = phones[currentIndex];
    const value = valuesFor(phone)[i];
    tooltip.innerHTML =
      '<span class="gm-radar-tt-cat">' + dim.icon + " " + dim.label + "</span>" +
      '<span class="gm-radar-tt-score">' + value.toFixed(1) + " / 10</span>" +
      '<span class="gm-radar-tt-explain">' + dim.explain + "</span>";
    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
    tooltip.classList.add("is-visible");
  }
  function hideTooltip() {
    tooltip.classList.remove("is-visible");
  }

  function bindDotHover(dot, i) {
    const enter = () => {
      dot.classList.add("is-hover");
      // Position tooltip relative to the chart wrapper using the dot's coords.
      const rect = svg.getBoundingClientRect();
      const scaleX = rect.width / SIZE;
      const scaleY = rect.height / SIZE;
      const x = parseFloat(dot.getAttribute("cx")) * scaleX;
      const y = parseFloat(dot.getAttribute("cy")) * scaleY;
      showTooltip(i, x, y);
    };
    const leave = () => { dot.classList.remove("is-hover"); hideTooltip(); };
    dot.addEventListener("mouseenter", enter);
    dot.addEventListener("mouseleave", leave);
    dot.addEventListener("focus", enter);
    dot.addEventListener("blur", leave);
    dot.setAttribute("tabindex", "0");
  }

  /* ---- legend (numeric values for every dimension) ---- */
  function renderLegend(values) {
    legend.innerHTML = DIMENSIONS.map((dim, i) => {
      const v = values[i];
      const pct = Math.round((v / MAX) * 100);
      return (
        '<div class="gm-insights-legend-row" data-dim="' + i + '" tabindex="0">' +
          '<span class="gm-insights-legend-label">' + dim.icon + " " + dim.label + "</span>" +
          '<div class="gm-insights-legend-track"><div class="gm-insights-legend-fill" style="width:' + pct + '%"></div></div>' +
          '<span class="gm-insights-legend-num">' + v.toFixed(1) + "</span>" +
        "</div>"
      );
    }).join("");

    // Hovering a legend row highlights the matching dot + shows its tooltip.
    legend.querySelectorAll(".gm-insights-legend-row").forEach((rowEl) => {
      const i = parseInt(rowEl.dataset.dim, 10);
      const enter = () => {
        const dot = dataDots[i];
        if (!dot) return;
        dot.classList.add("is-hover");
        const rect = svg.getBoundingClientRect();
        const x = parseFloat(dot.getAttribute("cx")) * (rect.width / SIZE);
        const y = parseFloat(dot.getAttribute("cy")) * (rect.height / SIZE);
        showTooltip(i, x, y);
      };
      const leave = () => { if (dataDots[i]) dataDots[i].classList.remove("is-hover"); hideTooltip(); };
      rowEl.addEventListener("mouseenter", enter);
      rowEl.addEventListener("mouseleave", leave);
      rowEl.addEventListener("focus", enter);
      rowEl.addEventListener("blur", leave);
    });

  }

  /* ---- select a recommendation ---- */
  function select(index, animate) {
    if (index < 0 || index >= phones.length) return;
    currentIndex = index;
    const values = valuesFor(phones[index]);

    // Tabs
    tabsWrap.querySelectorAll(".gm-insights-tab").forEach((tab) => {
      const active = parseInt(tab.dataset.index, 10) === index;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });

    drawData(values, animate);
    renderLegend(values);
    hideTooltip();
  }

  /* ---- init ---- */
  drawScaffold();
  select(0, false);

  tabsWrap.addEventListener("click", (e) => {
    const tab = e.target.closest(".gm-insights-tab");
    if (!tab) return;
    select(parseInt(tab.dataset.index, 10), true);
  });

  // Keyboard: left/right arrows switch recommendations when a tab is focused.
  tabsWrap.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const delta = e.key === "ArrowRight" ? 1 : -1;
    const next = (currentIndex + delta + phones.length) % phones.length;
    select(next, true);
    const nextTab = tabsWrap.querySelector('.gm-insights-tab[data-index="' + next + '"]');
    if (nextTab) nextTab.focus();
  });
});