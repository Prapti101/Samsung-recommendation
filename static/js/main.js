/* main.js — shared behaviour across all pages */

document.addEventListener("DOMContentLoaded", () => {
  // Gentle reveal animation for elements marked [data-reveal]
  const revealEls = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && revealEls.length) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.style.opacity = 1;
          entry.target.style.transform = "translateY(0)";
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    revealEls.forEach((el) => {
      el.style.opacity = 0;
      el.style.transform = "translateY(16px)";
      el.style.transition = "opacity .6s ease, transform .6s ease";
      io.observe(el);
    });
  }

  // Navbar: add .is-scrolled after a small scroll for the floating/shrink effect
  const navbar = document.getElementById("gm-navbar");
  if (navbar) {
    const onScroll = () => {
      navbar.classList.toggle("is-scrolled", window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Back-to-top button: reveal after scrolling, smooth-scroll to top on click.
  const toTop = document.getElementById("gm-backtotop");
  if (toTop) {
    const toggleTop = () => {
      toTop.classList.toggle("is-visible", window.scrollY > 600);
    };
    toggleTop();
    window.addEventListener("scroll", toggleTop, { passive: true });
    toTop.addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // Animated progress bars: fill when the container enters the viewport.
  // box never registers as intersecting).
  const barGroups = document.querySelectorAll(".gm-match-bars");
  if ("IntersectionObserver" in window && barGroups.length) {
    const barIO = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          barIO.unobserve(entry.target);
        }
      });
    }, { threshold: 0.3 });
    barGroups.forEach((group) => barIO.observe(group));
  }
});

/* Small helper: format a number as Indian Rupees with commas */
function gmFormatINR(num) {
  return "₹" + Number(num).toLocaleString("en-IN");
}