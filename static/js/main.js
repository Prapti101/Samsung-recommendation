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
});

/* Small helper: format a number as Indian Rupees with commas */
function gmFormatINR(num) {
  return "₹" + Number(num).toLocaleString("en-IN");
}
