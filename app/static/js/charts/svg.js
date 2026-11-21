(function () {
  "use strict";
  const ns = "http://www.w3.org/2000/svg";
  function element(name, attributes = {}) {
    const node = document.createElementNS(ns, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }
  function frame(label, width = 320, height = 120) {
    const svg = element("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": label, focusable: "false" });
    const title = element("title"); title.textContent = label; svg.append(title);
    return { svg, element };
  }
  function empty(svg, message = "Not enough data yet") {
    svg.classList.add("chart--empty");
    const text = element("text", { x: "50%", y: "55%", class: "chart-empty-label", "text-anchor": "middle" });
    text.textContent = message; svg.append(text); return svg;
  }
  window.BookingCharts = { element, frame, empty };
})();
