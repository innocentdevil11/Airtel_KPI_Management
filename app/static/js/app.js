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
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  return { ctx, width: rect.width, height: rect.height };
}

function drawBarChart(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const data = readChartData(id);
  const { ctx, width, height } = setupCanvas(canvas);
  const max = Math.max(...data.map(item => Number(item.total || 0)), 1);
  const colors = ["#2563eb", "#c42b2b", "#b7791f", "#16803c", "#64748b"];
  const gap = 14;
  const barWidth = Math.max(24, (width - gap * (data.length + 1)) / Math.max(data.length, 1));

  ctx.clearRect(0, 0, width, height);
  ctx.font = "12px Arial";
  ctx.fillStyle = "#64748b";

  data.forEach((item, index) => {
    const value = Number(item.total || 0);
    const barHeight = (height - 70) * value / max;
    const x = gap + index * (barWidth + gap);
    const y = height - 38 - barHeight;
    ctx.fillStyle = colors[index % colors.length];
    ctx.fillRect(x, y, barWidth, barHeight);
    ctx.fillStyle = "#162033";
    ctx.fillText(String(value), x, y - 6);
    ctx.fillStyle = "#64748b";
    ctx.fillText(String(item.label || "").slice(0, 16), x, height - 16);
  });
}

function drawLineChart(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const data = readChartData(id).filter(item => item.value_number !== null);
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  if (!data.length) {
    ctx.fillStyle = "#64748b";
    ctx.fillText("No numeric trend values found", 16, 32);
    return;
  }

  const values = data.map(item => Number(item.value_number));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  const points = data.map((item, index) => ({
    x: 24 + index * ((width - 48) / Math.max(data.length - 1, 1)),
    y: height - 36 - ((Number(item.value_number) - min) / span) * (height - 72),
    label: item.week_label
  }));

  ctx.strokeStyle = "#d9e2ef";
  ctx.beginPath();
  ctx.moveTo(24, 18);
  ctx.lineTo(24, height - 36);
  ctx.lineTo(width - 18, height - 36);
  ctx.stroke();

  ctx.strokeStyle = "#2563eb";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();

  ctx.fillStyle = "#2563eb";
  points.forEach(point => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

function setupTableSearch() {
  document.querySelectorAll("[data-table-search]").forEach(input => {
    const table = document.getElementById(input.dataset.tableSearch);
    if (!table) return;
    input.addEventListener("input", () => {
      const query = input.value.toLowerCase();
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
        const left = a.children[index].innerText.trim();
        const right = b.children[index].innerText.trim();
        return direction === "asc" ? left.localeCompare(right, undefined, { numeric: true }) : right.localeCompare(left, undefined, { numeric: true });
      });
      rows.forEach(row => tbody.appendChild(row));
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupTableSearch();
  setupTableSort();
});
