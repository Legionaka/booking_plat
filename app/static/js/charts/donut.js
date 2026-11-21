(function () {
  "use strict";
  const { element, frame } = window.BookingCharts;
  function draw(items, label) {
    const { svg } = frame(label, 180, 180);
    const total = (items || []).reduce((sum, item) => sum + Number(item.value || 0), 0);
    if (!total) return window.BookingCharts.empty(svg, "No bookings yet");
    const palette = ["chart-segment--pearl", "chart-segment--silver", "chart-segment--dim", "chart-segment--amber", "chart-segment--rose"];
    const circleLength = 2 * Math.PI * 56;
    svg.append(element("circle", { cx: 90, cy: 90, r: 56, class: "chart-donut-track" }));
    let offset = 0;
    items.forEach((item, index) => {
      const length = (Number(item.value) / total) * circleLength;
      svg.append(element("circle", { cx: 90, cy: 90, r: 56, class: `chart-donut-segment ${palette[index % palette.length]}`, "stroke-dasharray": `${length} ${circleLength - length}`, "stroke-dashoffset": -offset }));
      offset += length;
    });
    return svg;
  }
  window.BookingCharts.donut = draw;
})();
