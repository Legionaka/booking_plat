(function () {
  "use strict";
  const { element, frame } = window.BookingCharts;
  function draw(cells, label = "Booking activity heatmap") {
    const { svg } = frame(label, 520, 190);
    const values = (cells || []).map((item) => Number(item.value || 0));
    const max = Math.max(...values, 0);
    if (!max) return window.BookingCharts.empty(svg, "No activity yet");
    (cells || []).forEach((cell, index) => {
      const value = Number(cell.value || 0);
      const step = value ? Math.min(5, Math.ceil((value / max) * 5)) : 0;
      const rect = element("rect", { x: (index % 14) * 35 + 2, y: Math.floor(index / 14) * 30 + 4, width: 27, height: 22, rx: 4, class: `chart-heatmap__cell chart-heatmap__cell--${step}` });
      rect.setAttribute("aria-label", `${cell.label || `Period ${index + 1}`}: ${value}`); svg.append(rect);
    });
    return svg;
  }
  window.BookingCharts.heatmap = draw;
})();
