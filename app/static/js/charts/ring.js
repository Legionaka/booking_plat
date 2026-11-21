(function () {
  "use strict";
  const { element, frame } = window.BookingCharts;
  function draw(value, label) {
    const { svg } = frame(label, 120, 120);
    const ratio = Math.max(0, Math.min(1, Number(value) / 100));
    svg.append(element("circle", { cx: 60, cy: 60, r: 42, class: "chart-ring-track" }));
    svg.append(element("circle", { cx: 60, cy: 60, r: 42, class: "chart-ring-value", "stroke-dasharray": `${ratio * 264} 264`, "stroke-dashoffset": 66 }));
    const text = element("text", { x: 60, y: 65, class: "chart-ring-label", "text-anchor": "middle" }); text.textContent = `${Math.round(ratio * 100)}%`; svg.append(text);
    return svg;
  }
  window.BookingCharts.ring = draw;
})();
