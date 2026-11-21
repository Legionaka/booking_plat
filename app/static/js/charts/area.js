(function () {
  "use strict";
  const { element, frame } = window.BookingCharts;
  function draw(values, label) {
    const { svg } = frame(label, 640, 220);
    if (!values || values.length < 2 || !values.some((item) => Number(item.value) > 0)) {
      return window.BookingCharts.empty(svg, "Not enough data for this period");
    }
    const max = Math.max(...values.map((item) => Number(item.value)), 1);
    const points = values.map((item, index) => `${20 + (index / (values.length - 1)) * 600},${190 - (Number(item.value) / max) * 160}`);
    svg.append(element("line", { x1: 20, y1: 190, x2: 620, y2: 190, class: "chart-axis" }));
    svg.append(element("polyline", { points: points.join(" "), class: "chart-area-line" }));
    points.forEach((point) => { const [cx, cy] = point.split(","); svg.append(element("circle", { cx, cy, r: 3, class: "chart-point" })); });
    return svg;
  }
  window.BookingCharts.area = draw;
})();
