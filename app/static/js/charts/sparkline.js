(function () {
  "use strict";
  function draw(values, label) {
    const { svg, element } = window.BookingCharts.frame(label, 160, 44);
    if (!values || values.length < 2) return window.BookingCharts.empty(svg);
    const max = Math.max(...values, 1), min = Math.min(...values, 0);
    const points = values.map((value, index) => `${(index / (values.length - 1)) * 156 + 2},${40 - ((value - min) / (max - min || 1)) * 36}`).join(" ");
    svg.append(element("polyline", { points, class: "chart-sparkline" }));
    return svg;
  }
  const { element } = window.BookingCharts;
  window.BookingCharts.sparkline = draw;
})();
