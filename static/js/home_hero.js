/* home_hero.js — premium homepage hero + collection carousel
 * ----------------------------------------------------------
 * Purely presentational. Adds:
 *   1. A rotating flagship phone (CSS 3D illusion) with idle spin,
 *      drag/swipe to rotate 360° with inertia, and auto phone-cycling
 *      every ~9s (updating headline accent, tagline, series, name, colour).
 *   2. A "Latest Galaxy Collection" configurator carousel (drag/swipe/arrows,
 *      snap, autoplay, centre card largest).
 *
 * Independent of home.js — it touches only its own DOM ids. No backend calls,
 * no recommendation logic. Phone data below is display-only showcase content.
 */

(function () {
  "use strict";

  // Display-only flagship dataset (name / series / tagline / accent / colour).
  const PHONES = [
    { name: "Galaxy S25 Ultra", series: "Galaxy S", tagline: "Built for creators — the ultimate camera flagship.", accent: "#2F6FED", body: "linear-gradient(150deg,#2a2f3a,#0e1118)", img: "s25_ultra", isNew: true,  price: "₹1,34,999" },
    { name: "Galaxy Z Fold6",   series: "Galaxy Z", tagline: "Unfold more — a tablet and phone in one.",           accent: "#6C5CE7", body: "linear-gradient(150deg,#20242c,#0b0d12)", img: "z_fold6",   isNew: true,  price: "₹1,64,999" },
    { name: "Galaxy Z Flip6",   series: "Galaxy Z", tagline: "Compact powerhouse that flips the script.",          accent: "#E84393", body: "linear-gradient(150deg,#2b2530,#120d14)", img: "z_flip6",   isNew: true,  price: "₹1,09,999" },
    { name: "Galaxy S24 FE",    series: "Galaxy S", tagline: "Flagship experience, everyday value.",               accent: "#00B894", body: "linear-gradient(150deg,#1f2a2a,#0a1010)", img: "s24_fe",    isNew: false, price: "₹59,999" },
    { name: "Galaxy A55 5G",    series: "Galaxy A", tagline: "Power meets value in the everyday hero.",            accent: "#0984E3", body: "linear-gradient(150deg,#232a33,#0c1016)", img: "a55",      isNew: false, price: "₹39,999" },
    { name: "Galaxy M55 5G",    series: "Galaxy M", tagline: "Endurance-first, made to keep going.",               accent: "#E17055", body: "linear-gradient(150deg,#2a2320,#120c0a)", img: "m55",      isNew: false, price: "₹26,999" },
  ];
  const IMG_BASE = "/static/img/";

  const reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------
     HERO: premium idle phone showcase.
     Floats + slowly rotates on a tilted axis, gently sways, casts a soft
     dynamic shadow, and reacts to mouse/touch with a small parallax tilt.
     No arrows, no cycling — a clean, self-animating product showcase.
     --------------------------------------------------------------- */
  function initHero() {
    const stage = document.getElementById("gm-lux-stage");
    const phone = document.getElementById("gm-lux-phone");
    const wrap = document.getElementById("gm-lux-phone-wrap");
    const shadow = stage ? stage.querySelector(".gm-lux-stage-shadow") : null;
    if (!stage || !phone) return;

    let t = 0;                 // animation clock
    let pointerX = 0, pointerY = 0;   // normalised pointer (-1..1)
    let targetX = 0, targetY = 0;     // eased pointer targets
    let running = true;

    function frame() {
      if (!running) return;
      t += 0.016;

      // Ease pointer influence for smooth, non-robotic motion.
      pointerX += (targetX - pointerX) * 0.06;
      pointerY += (targetY - pointerY) * 0.06;

      // Constant, elegant 360° pivot around the vertical axis (~one turn / 9s),
      // with a gentle vertical float. Pointer adds only a subtle depth tilt.
      const rotY = reduceMotion ? -18 : t * 40;                 // continuous spin
      const floatY = reduceMotion ? 0 : Math.sin(t * 1.1) * 10; // vertical float (px)
      const tiltX = -4 + pointerY * -4;                         // slight fixed tilt + tiny parallax

      phone.style.transform =
        "rotateX(" + tiltX.toFixed(2) + "deg) rotateY(" + rotY.toFixed(2) + "deg)";
      if (wrap) wrap.style.transform = "translateY(" + floatY.toFixed(2) + "px)";

      // Soft dynamic shadow: shrinks as the phone rises, drifts with pointer.
      if (shadow) {
        const lift = (floatY + 10) / 20;                 // 0..1
        const w = 210 - lift * 34;
        const op = 0.5 - lift * 0.16;
        shadow.style.width = w.toFixed(0) + "px";
        shadow.style.opacity = op.toFixed(2);
        shadow.style.transform =
          "translateX(calc(-50% + " + (pointerX * 12).toFixed(1) + "px))";
      }

      requestAnimationFrame(frame);
    }

    // Pointer tracking (parallax tilt) — desktop
    stage.addEventListener("mousemove", (e) => {
      const r = stage.getBoundingClientRect();
      targetX = ((e.clientX - r.left) / r.width) * 2 - 1;
      targetY = ((e.clientY - r.top) / r.height) * 2 - 1;
    });
    stage.addEventListener("mouseleave", () => { targetX = 0; targetY = 0; });

    // Touch tracking — mobile
    stage.addEventListener("touchmove", (e) => {
      const tch = e.touches[0];
      if (!tch) return;
      const r = stage.getBoundingClientRect();
      targetX = ((tch.clientX - r.left) / r.width) * 2 - 1;
      targetY = ((tch.clientY - r.top) / r.height) * 2 - 1;
    }, { passive: true });
    stage.addEventListener("touchend", () => { targetX = 0; targetY = 0; });

    // Pause the loop when the tab is hidden (perf).
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        running = false;
      } else if (!running) {
        running = true;
        requestAnimationFrame(frame);
      }
    });

    requestAnimationFrame(frame);
  }

  /* ---------------------------------------------------------------
     COLLECTION: configurator carousel
     --------------------------------------------------------------- */
  function initCarousel() {
    const track = document.getElementById("gm-lux-track");
    const carousel = document.getElementById("gm-lux-carousel");
    if (!track || !carousel) return;

    const prevBtn = document.getElementById("gm-lux-carousel-prev");
    const nextBtn = document.getElementById("gm-lux-carousel-next");

    // Latest five (exclude the last budget item to keep it "latest")
    const items = PHONES.slice(0, 5);

    function badgeClass(series) {
      return "gm-lux-badge--" + series.replace("Galaxy ", "").toLowerCase();
    }

    function cardHtml(p) {
      return (
        '<article class="gm-lux-card" role="listitem" tabindex="0">' +
          '<div class="gm-lux-card-media">' +
            (p.isNew ? '<span class="gm-lux-new">NEW</span>' : "") +
            '<span class="gm-lux-badge ' + badgeClass(p.series) + '">' + p.series + "</span>" +
            '<img class="gm-lux-card-img" src="' + IMG_BASE + p.img + '.webp" alt="' + p.name + '" loading="lazy">' +
          "</div>" +
          '<div class="gm-lux-card-body">' +
            '<h3 class="gm-lux-card-name">' + p.name + "</h3>" +
            '<p class="gm-lux-card-tag">' + p.tagline + "</p>" +
            '<div class="gm-lux-card-foot">' +
              '<span class="gm-lux-card-price">' + p.price + '<small>onwards</small></span>' +
              '<a href="#build" class="gm-lux-card-btn">Explore phone <i class="bi bi-arrow-right"></i></a>' +
            "</div>" +
          "</div>" +
        "</article>"
      );
    }

    // Duplicate the set for a seamless infinite-feeling loop.
    track.innerHTML = items.map(cardHtml).join("") + items.map(cardHtml).join("");
    const cards = Array.from(track.children);

    // Centre-largest scaling based on distance from viewport centre.
    let raf = null;
    function updateScale() {
      const rect = carousel.getBoundingClientRect();
      const centre = rect.left + rect.width / 2;
      cards.forEach((card) => {
        const cr = card.getBoundingClientRect();
        const cc = cr.left + cr.width / 2;
        const dist = Math.abs(centre - cc);
        const norm = Math.min(dist / (rect.width / 1.6), 1);
        const scale = 1 - norm * 0.16;
        const opacity = 1 - norm * 0.45;
        card.style.transform = "scale(" + scale.toFixed(3) + ")";
        card.style.opacity = opacity.toFixed(3);
        card.classList.toggle("is-centre", norm < 0.18);
      });
      raf = null;
    }
    function requestUpdate() {
      if (!raf) raf = requestAnimationFrame(updateScale);
    }

    // Drag-to-scroll
    let down = false, startX = 0, startScroll = 0, moved = false;
    track.addEventListener("mousedown", (e) => {
      down = true; moved = false; startX = e.pageX;
      startScroll = track.scrollLeft; track.classList.add("is-grabbing");
    });
    window.addEventListener("mousemove", (e) => {
      if (!down) return;
      const dx = e.pageX - startX;
      if (Math.abs(dx) > 4) moved = true;
      track.scrollLeft = startScroll - dx;
    });
    window.addEventListener("mouseup", () => { down = false; track.classList.remove("is-grabbing"); });
    // Prevent click navigation right after a drag
    track.addEventListener("click", (e) => { if (moved) e.preventDefault(); }, true);

    track.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);

    function scrollByCard(dir) {
      const card = cards[0];
      const step = card ? card.offsetWidth + 24 : 320;
      track.scrollBy({ left: dir * step, behavior: "smooth" });
    }
    prevBtn.addEventListener("click", () => scrollByCard(-1));
    nextBtn.addEventListener("click", () => scrollByCard(1));

    // Autoplay (pauses on hover / interaction)
    let auto = null;
    function startAuto() {
      if (reduceMotion) return;
      stopAuto();
      auto = setInterval(() => {
        const maxScroll = track.scrollWidth - track.clientWidth;
        if (track.scrollLeft >= maxScroll - 4) {
          track.scrollTo({ left: 0, behavior: "smooth" });
        } else {
          scrollByCard(1);
        }
      }, 3800);
    }
    function stopAuto() { if (auto) clearInterval(auto); auto = null; }
    carousel.addEventListener("mouseenter", stopAuto);
    carousel.addEventListener("mouseleave", startAuto);
    carousel.addEventListener("touchstart", stopAuto, { passive: true });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stopAuto(); else startAuto();
    });

    // Centre the first "hero" card initially.
    requestAnimationFrame(() => {
      const first = cards[0];
      if (first) {
        const offset = first.offsetLeft - (carousel.clientWidth - first.offsetWidth) / 2;
        track.scrollLeft = Math.max(0, offset);
      }
      updateScale();
      startAuto();
    });
  }

  function init() { initHero(); initCarousel(); }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();