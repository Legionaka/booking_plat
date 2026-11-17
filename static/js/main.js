"use strict";

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

if (!reducedMotion.matches && window.PointerEvent) {
  document.querySelectorAll(".glass").forEach((surface) => {
    surface.addEventListener("pointermove", (event) => {
      const bounds = surface.getBoundingClientRect();
      const x = ((event.clientX - bounds.left) / bounds.width) * 100;
      const y = ((event.clientY - bounds.top) / bounds.height) * 100;
      surface.style.setProperty("--mx", `${Math.max(0, Math.min(100, x))}%`);
      surface.style.setProperty("--my", `${Math.max(0, Math.min(100, y))}%`);
    });
  });
}
