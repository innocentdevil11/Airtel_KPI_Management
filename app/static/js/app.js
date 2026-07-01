const STATUS_COLORS = {
  Critical: "#dc2626",
  Warning: "#d97706",
  Healthy: "#16a34a",
  Pending: "#64748b",
  kpi: "#2563eb",
  utilization: "#0f766e",
  Uncategorized: "#7c3aed"
};
const PALETTE = ["#2563eb", "#dc2626", "#d97706", "#16a34a", "#0f766e", "#7c3aed", "#475569", "#be185d"];

function readChartData(id) {
  const node = document.getElementById(id);
  if (!node) return [];
  try {
    return JSON.parse(node.dataset.chart || "[]");
  } catch {
    return [];
  }
}

function setupCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(rect.width, 320);
  const height = Math.max(rect.height, 220);
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

function colorFor(label, index) {
  return STATUS_COLORS[label] || PALETTE[index % PALETTE.length];
}

function drawEmpty(ctx, message) {
  ctx.fillStyle = "#64748b";
  ctx.font = "14px Arial";
  ctx.fillText(message, 18, 34);
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, Math.abs(height) / 2, Math.abs(width) / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

function shorten(text, max = 22) {
  const value = String(text || "");
  return value.length > max ? `${value.slice(0, max - 1)}...` : value;
}

function drawDoughnutChart(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const data = readChartData(id).filter(item => Number(item.total || 0) > 0);
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  if (!data.length) return drawEmpty(ctx, "No chart data yet");

  const total = data.reduce((sum, item) => sum + Number(item.total || 0), 0);
  const radius = Math.min(width * 0.28, height * 0.36, 96);
  const cx = Math.min(width * 0.34, 150);
  const cy = height / 2;
  let start = -Math.PI / 2;

  data.forEach((item, index) => {
    const value = Number(item.total || 0);
    const end = start + (value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, start, end);
    ctx.closePath();
    ctx.fillStyle = colorFor(item.label, index);
    ctx.fill();
    start = end;
  });

  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.58, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();
  ctx.fillStyle = "#0f172a";
  ctx.font = "700 24px Arial";
  ctx.textAlign = "center";
  ctx.fillText(String(total), cx, cy + 7);
  ctx.font = "12px Arial";
  ctx.fillStyle = "#64748b";
  ctx.fillText("total", cx, cy + 27);

  ctx.textAlign = "left";
  let legendY = 38;
  data.forEach((item, index) => {
    const x = Math.min(width * 0.58, 250);
    ctx.fillStyle = colorFor(item.label, index);
    roundRect(ctx, x, legendY - 10, 12, 12, 3);
    ctx.fill();
    ctx.fillStyle = "#334155";
    ctx.font = "13px Arial";
    ctx.fillText(`${shorten(item.label, 18)} (${item.total})`, x + 20, legendY);
    legendY += 24;
  });
}

function drawHorizontalBarChart(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const data = readChartData(id).slice(0, 12);
  canvas.style.height = `${Math.max(280, data.length * 34 + 70)}px`;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  if (!data.length) return drawEmpty(ctx, "No chart data yet");

  const labelWidth = Math.min(190, Math.max(120, width * 0.28));
  const chartWidth = width - labelWidth - 54;
  const max = Math.max(...data.map(item => Number(item.total || 0)), 1);
  const rowHeight = Math.max(26, (height - 50) / data.length);

  ctx.font = "12px Arial";
  data.forEach((item, index) => {
    const value = Number(item.total || 0);
    const y = 28 + index * rowHeight;
    const barWidth = (value / max) * chartWidth;
    ctx.fillStyle = "#475569";
    ctx.textAlign = "right";
    ctx.fillText(shorten(item.label, 24), labelWidth - 10, y + 15);
    ctx.fillStyle = "#e2e8f0";
    roundRect(ctx, labelWidth, y, chartWidth, 17, 8);
    ctx.fill();
    ctx.fillStyle = colorFor(item.label, index);
    roundRect(ctx, labelWidth, y, Math.max(barWidth, 5), 17, 8);
    ctx.fill();
    ctx.fillStyle = "#0f172a";
    ctx.textAlign = "left";
    ctx.fillText(String(value), labelWidth + barWidth + 8, y + 14);
  });
}

function drawStackedStatusChart(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const data = readChartData(id);
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  if (!data.length) return drawEmpty(ctx, "No week-wise status data yet");

  const keys = ["critical", "warning", "healthy", "pending"];
  const labels = ["Critical", "Warning", "Healthy", "Pending"];
  const totals = data.map(item => keys.reduce((sum, key) => sum + Number(item[key] || 0), 0));
  const max = Math.max(...totals, 1);
  const left = 34;
  const bottom = height - 42;
  const chartHeight = height - 74;
  const gap = 10;
  const barWidth = Math.max(18, (width - left - 24 - gap * (data.length - 1)) / Math.max(data.length, 1));

  ctx.strokeStyle = "#e2e8f0";
  ctx.beginPath();
  ctx.moveTo(left, 18);
  ctx.lineTo(left, bottom);
  ctx.lineTo(width - 16, bottom);
  ctx.stroke();

  data.forEach((item, index) => {
    let y = bottom;
    const x = left + 10 + index * (barWidth + gap);
    keys.forEach((key, keyIndex) => {
      const value = Number(item[key] || 0);
      const h = (value / max) * chartHeight;
      y -= h;
      ctx.fillStyle = colorFor(labels[keyIndex], keyIndex);
      ctx.fillRect(x, y, barWidth, h);
    });
    ctx.fillStyle = "#64748b";
    ctx.font = "11px Arial";
    ctx.textAlign = "center";
    ctx.fillText(shorten(item.label, 9), x + barWidth / 2, bottom + 18);
  });
}

function drawTrendChart(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const data = readChartData(id).filter(item => item.value_number !== null && item.value_number !== undefined);
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  if (!data.length) return drawEmpty(ctx, "No numeric trend values found");

  const values = data.map(item => Number(item.value_number));
  const thresholds = data.map(item => Number(item.threshold)).filter(value => !Number.isNaN(value));
  const allValues = values.concat(thresholds);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const padding = Math.max((max - min) * 0.12, 1);
  const low = min - padding;
  const high = max + padding;
  const span = Math.max(high - low, 1);
  const left = 42;
  const right = width - 22;
  const top = 22;
  const bottom = height - 48;

  const pointFor = (value, index) => ({
    x: left + index * ((right - left) / Math.max(data.length - 1, 1)),
    y: bottom - ((Number(value) - low) / span) * (bottom - top)
  });

  ctx.strokeStyle = "#e2e8f0";
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = top + i * ((bottom - top) / 3);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }

  if (thresholds.length) {
    ctx.strokeStyle = "#d97706";
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    data.forEach((item, index) => {
      const threshold = Number(item.threshold);
      if (Number.isNaN(threshold)) return;
      const point = pointFor(threshold, index);
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const gradient = ctx.createLinearGradient(0, top, 0, bottom);
  gradient.addColorStop(0, "rgba(37, 99, 235, .28)");
  gradient.addColorStop(1, "rgba(37, 99, 235, 0)");
  const points = values.map((value, index) => pointFor(value, index));
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.lineTo(points[points.length - 1].x, bottom);
  ctx.lineTo(points[0].x, bottom);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.strokeStyle = "#2563eb";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();

  points.forEach((point, index) => {
    ctx.fillStyle = colorFor(data[index].status, index);
    ctx.beginPath();
    ctx.arc(point.x, point.y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#0f172a";
    ctx.font = "11px Arial";
    ctx.textAlign = "center";
    ctx.fillText(String(data[index].value_number), point.x, point.y - 10);
    ctx.fillStyle = "#64748b";
    ctx.fillText(shorten(data[index].week_label, 10), point.x, bottom + 20);
  });

  ctx.textAlign = "left";
  ctx.fillStyle = "#2563eb";
  ctx.fillText("Value", left, 14);
  if (thresholds.length) {
    ctx.fillStyle = "#d97706";
    ctx.fillText("Threshold", left + 56, 14);
  }
}

function drawBarChart(id) {
  drawHorizontalBarChart(id);
}

function setupTableSearch() {
  document.querySelectorAll("[data-table-search]").forEach(input => {
    const table = document.getElementById(input.dataset.tableSearch);
    if (!table) return;
    input.addEventListener("input", () => {
      const query = input.value.toLowerCase().trim();
      table.querySelectorAll("tbody tr").forEach(row => {
        row.style.display = row.innerText.toLowerCase().includes(query) ? "" : "none";
      });
    });
  });
}

function setupTableSort() {
  document.querySelectorAll(".data-table th").forEach((header, index) => {
    header.addEventListener("click", () => {
      const table = header.closest("table");
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const direction = header.dataset.direction === "asc" ? "desc" : "asc";
      header.dataset.direction = direction;
      rows.sort((a, b) => {
        const left = a.children[index]?.innerText.trim() || "";
        const right = b.children[index]?.innerText.trim() || "";
        return direction === "asc" ? left.localeCompare(right, undefined, { numeric: true }) : right.localeCompare(left, undefined, { numeric: true });
      });
      rows.forEach(row => tbody.appendChild(row));
    });
  });
}

function setupActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll(".sidebar a").forEach(link => {
    const href = link.getAttribute("href");
    if (href === path || (href !== "/" && path.startsWith(href))) {
      link.classList.add("active");
    }
  });
}

function setupReveal() {
  const items = document.querySelectorAll(".reveal");
  if (!items.length) return;
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });
  items.forEach(item => observer.observe(item));
}

document.addEventListener("DOMContentLoaded", () => {
  setupTableSearch();
  setupTableSort();
  setupActiveNav();
  setupReveal();
});
