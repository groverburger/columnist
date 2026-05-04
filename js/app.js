// ============================== CONSTANTS ==============================
const COLORS = {
  bg:        '#131722',
  chartBg:   '#131722',
  axisBg:    '#1e222d',
  grid:      '#1e2230',
  text:      '#d1d4dc',
  textDim:   '#787b86',
  up:        '#26a69a',
  down:      '#ef5350',
  crosshair: '#555b66',
  crossLabel:'#2962ff',
};
const BASE_CW = 20;
const BASE_RH = 20;
const MARGIN = { top: 8, right: 82, bottom: 28, left: 6 };

// ============================== STATE ==============================
let ohlcData = [];
let pnf = null;        // { columns, columnDates, columnDirections }
let rowInfo = null;     // { minRow, maxRow, priceToRow, rowToPrice }
let currentTicker = '';
let lastClose = 0;

let zoom = 1, panX = 0, panY = 0;
let isDragging = false, dragStartX = 0, dragStartY = 0, panStartX = 0, panStartY = 0;
let mouseX = -1, mouseY = -1;
let isLoading = false;
let activePeriod = '2y';
let appSettings = { version: 1, watchlists: [], tickerSettings: {} };
let selectedWatchlistId = 'default';
let activityByTicker = {};
let activityScanToken = 0;
let collapsedCats = new Set();
let draggedWatchlistIndex = null;
let suppressTickerClickUntil = 0;

const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');
let dpr = 1, canvasW = 0, canvasH = 0;

// ============================== SETTINGS ==============================
function normalizeTicker(t) {
  return (t || '').trim().toUpperCase();
}
function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
function defaultWatchlist() {
  return {
    id: 'default',
    name: 'Default',
    symbols: ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'GLD', 'TLT', 'USO', 'BTC-USD'],
    readonly: true
  };
}
function ensureSettingsShape() {
  if (!appSettings || typeof appSettings !== 'object') appSettings = {};
  if (!Array.isArray(appSettings.watchlists)) appSettings.watchlists = [defaultWatchlist()];
  if (!appSettings.watchlists.some(w => w.id === 'default')) appSettings.watchlists.unshift(defaultWatchlist());
  appSettings.watchlists = appSettings.watchlists.map((w, i) => ({
    id: w.id || ('wl-' + i),
    name: w.name || 'Watchlist',
    symbols: Array.isArray(w.symbols) ? Array.from(new Set(w.symbols.map(normalizeTicker).filter(Boolean))) : [],
    readonly: !!w.readonly
  }));
  const def = appSettings.watchlists.find(w => w.id === 'default');
  if (def) {
    def.name = def.name || 'Default';
    def.readonly = true;
    if (!def.symbols.length) def.symbols = defaultWatchlist().symbols;
  }
  if (!appSettings.tickerSettings || typeof appSettings.tickerSettings !== 'object') appSettings.tickerSettings = {};
}
async function loadSettings() {
  try {
    const resp = await fetch('/api/settings');
    appSettings = await resp.json();
  } catch(e) {
    appSettings = { version: 1, watchlists: [defaultWatchlist()], tickerSettings: {} };
  }
  ensureSettingsShape();
  migrateLocalBoxSizes();
}
function migrateLocalBoxSizes() {
  try {
    const old = JSON.parse(localStorage.getItem('pnfBoxSizes')) || {};
    let changed = false;
    for (const [ticker, boxSize] of Object.entries(old)) {
      const key = normalizeTicker(ticker);
      if (!appSettings.tickerSettings[key]) appSettings.tickerSettings[key] = {};
      if (!appSettings.tickerSettings[key].boxSize) {
        appSettings.tickerSettings[key].boxSize = String(boxSize);
        changed = true;
      }
    }
    if (changed) saveSettings();
  } catch(e) {}
}
function saveSettings() {
  ensureSettingsShape();
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(appSettings)
  }).catch(() => {});
}
function getTickerSettings(ticker) {
  const key = normalizeTicker(ticker);
  if (!appSettings.tickerSettings[key]) appSettings.tickerSettings[key] = {};
  return appSettings.tickerSettings[key];
}
function saveCurrentTickerSettings() {
  if (!currentTicker) return;
  const settings = getTickerSettings(currentTicker);
  settings.boxSize = document.getElementById('box-size-select').value;
  settings.reversal = document.getElementById('reversal-select').value;
  saveSettings();
}
function getWatchlist(id) {
  ensureSettingsShape();
  return appSettings.watchlists.find(w => w.id === id) || appSettings.watchlists[0];
}

// ============================== PNF ALGORITHM ==============================
function round4(x) { return Math.round(x * 10000) / 10000; }

function generatePnF(data, bs, rs) {
  if (!data || data.length === 0) return null;

  function inc(p, n) { n = n || 1; for (let i = 0; i < n; i++) p = round4(p * (1 + bs)); return p; }
  function dec(p, n) { n = n || 1; for (let i = 0; i < n; i++) p = round4(p / (1 + bs)); return p; }

  let dir = 'up';
  const fc = data[0].close;
  let cols = [[fc]];
  let bxDates = [[data[0].date]];
  let dates = [data[0].date];
  let dirs = ['up'];
  let bp = 100;
  let curDate = data[0].date;

  while (fc > bp) bp = inc(bp);
  while (fc < bp) bp = dec(bp);

  function fillUp(price) {
    let f = false;
    while (price >= inc(bp)) { bp = inc(bp); cols[cols.length-1].push(bp); bxDates[bxDates.length-1].push(curDate); f = true; }
    return f;
  }
  function fillDown(price) {
    let f = false;
    while (price <= dec(bp)) { bp = dec(bp); cols[cols.length-1].push(bp); bxDates[bxDates.length-1].push(curDate); f = true; }
    return f;
  }
  function fill(price) { return dir === 'up' ? fillUp(price) : fillDown(price); }

  for (let i = 0; i < data.length; i++) {
    curDate = data[i].date;
    const h = data[i].high, l = data[i].low;
    if (dir === 'up') {
      if (fill(h)) continue;
      if (l <= dec(bp, rs)) {
        dir = 'down'; dirs.push(dir); cols.push([]); bxDates.push([]); dates.push(data[i].date);
        fill(l); continue;
      }
    }
    if (dir === 'down') {
      if (fill(l)) continue;
      if (h >= inc(bp, rs)) {
        dir = 'up'; dirs.push(dir); cols.push([]); bxDates.push([]); dates.push(data[i].date);
        fill(h); continue;
      }
    }
  }
  return { columns: cols, boxDates: bxDates, columnDates: dates, columnDirections: dirs };
}

function pruneEmptyColumns(p) {
  if (!p) return p;
  while (p.columns.length > 0 && p.columns[p.columns.length-1].length === 0) {
    p.columns.pop(); p.boxDates.pop(); p.columnDates.pop(); p.columnDirections.pop();
  }
  return p;
}

function analyzeDailyActivity(data, ticker) {
  if (!data || data.length === 0) return null;
  const settings = getTickerSettings(ticker);
  const bs = parseFloat(settings.boxSize || '0.01');
  const rs = parseInt(settings.reversal || '3');
  const p = pruneEmptyColumns(generatePnF(data, bs, rs));
  if (!p || p.columns.length === 0) return null;

  const latestDate = data[data.length - 1].date;
  let count = 0;
  let up = 0;
  let down = 0;
  let lastDir = '';
  let columnChanged = false;

  for (let ci = 0; ci < p.columns.length; ci++) {
    if (ci > 0 && p.columnDates[ci] === latestDate) columnChanged = true;
    const dir = p.columnDirections[ci];
    const dates = p.boxDates[ci] || [];
    for (let bi = 0; bi < dates.length; bi++) {
      if (dates[bi] !== latestDate) continue;
      count++;
      lastDir = dir;
      if (dir === 'up') up++; else down++;
    }
  }
  if (count === 0 && !columnChanged) return null;

  const dirLabel = lastDir === 'up' ? 'X' : 'O';
  const mixed = up > 0 && down > 0;
  const label = columnChanged
    ? 'REV ' + dirLabel
    : mixed ? count + 'x' : (count > 1 ? count : '') + dirLabel;
  const className = columnChanged ? 'rev' : mixed ? 'mixed' : lastDir === 'up' ? 'up' : 'down';
  const title = columnChanged
    ? 'Column changed on ' + latestDate + ' with ' + count + ' new ' + dirLabel + (count === 1 ? '' : 's')
    : count + ' new ' + dirLabel + (count === 1 ? '' : 's') + ' on ' + latestDate;
  return { label, className, title, date: latestDate, count, columnChanged };
}

// ============================== ROW MATH ==============================
function computeRowInfo(p, bs) {
  const lb = Math.log(1 + bs);
  let mn = Infinity, mx = -Infinity;
  for (const c of p.columns) for (const v of c) { mn = Math.min(mn, v); mx = Math.max(mx, v); }
  const minR = Math.round(Math.log(mn) / lb);
  const maxR = Math.round(Math.log(mx) / lb);
  return {
    minRow: minR, maxRow: maxR,
    priceToRow: function(pr) { return Math.round(Math.log(pr) / lb); },
    rowToPrice: function(r) { return Math.pow(1 + bs, r); },
    minPrice: mn, maxPrice: mx
  };
}

// ============================== COORDINATE TRANSFORMS ==============================
function cw() { return BASE_CW * zoom; }
function rh() { return BASE_RH * zoom; }
function w2sx(col) { return panX + col * cw(); }
function w2sy(row) { return panY + (rowInfo.maxRow - row) * rh(); }
function s2wCol(sx) { return (sx - panX) / cw(); }
function s2wRow(sy) { return rowInfo.maxRow - (sy - panY) / rh(); }
function chartLeft() { return MARGIN.left; }
function chartRight() { return canvasW - MARGIN.right; }
function chartTop() { return MARGIN.top; }
function chartBottom() { return canvasH - MARGIN.bottom; }
function chartW() { return chartRight() - chartLeft(); }
function chartH() { return chartBottom() - chartTop(); }

// ============================== RENDERING ==============================
function render() {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvasW, canvasH);

  // Background
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, canvasW, canvasH);

  if (!pnf || !rowInfo) {
    ctx.fillStyle = COLORS.textDim;
    ctx.font = '15px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Enter a ticker and press Load', canvasW / 2, canvasH / 2);
    return;
  }

  const CW = cw(), RH = rh();
  const totalCols = pnf.columns.length;
  const totalRows = rowInfo.maxRow - rowInfo.minRow + 1;
  const cL = chartLeft(), cR = chartRight(), cT = chartTop(), cB = chartBottom();

  // Axis backgrounds
  ctx.fillStyle = COLORS.axisBg;
  ctx.fillRect(cR, 0, MARGIN.right, canvasH);
  ctx.fillRect(0, cB, canvasW, MARGIN.bottom);

  // Clip to chart area for grid + boxes
  ctx.save();
  ctx.beginPath();
  ctx.rect(cL, cT, cR - cL, cB - cT);
  ctx.clip();

  // --- Grid ---
  // Horizontal grid lines
  let rowStep = 1;
  const niceSteps = [1,2,5,10,20,25,50,100,200,500,1000,2000,5000];
  for (const s of niceSteps) { if (s * RH >= 50) { rowStep = s; break; } }
  ctx.strokeStyle = COLORS.grid;
  ctx.lineWidth = 1;
  for (let r = rowInfo.minRow; r <= rowInfo.maxRow; r++) {
    if (r % rowStep !== 0) continue;
    const y = w2sy(r) + RH / 2;
    if (y < cT - 5 || y > cB + 5) continue;
    ctx.beginPath(); ctx.moveTo(cL, y); ctx.lineTo(cR, y); ctx.stroke();
  }

  // Vertical grid lines
  let colStep = 1;
  for (const s of niceSteps) { if (s * CW >= 80) { colStep = s; break; } }
  for (let c = 0; c < totalCols; c++) {
    if (c % colStep !== 0) continue;
    const x = w2sx(c) + CW / 2;
    if (x < cL - 5 || x > cR + 5) continue;
    ctx.beginPath(); ctx.moveTo(x, cT); ctx.lineTo(x, cB); ctx.stroke();
  }

  // --- Hover state (computed before drawing so highlights appear behind symbols) ---
  const inChart = mouseX >= cL && mouseX <= cR && mouseY >= cT && mouseY <= cB;
  let hoverCol = -1, hoverRow = -1, hoverPrice = 0;
  let hoverBoxInfo = null; // { date, indices[], prices[], dir }
  if (inChart && !isDragging) {
    hoverCol = Math.floor(s2wCol(mouseX));
    hoverRow = Math.ceil(s2wRow(mouseY));
    hoverPrice = rowInfo.rowToPrice(hoverRow);

    // Detect if cursor is over an actual box
    if (hoverCol >= 0 && hoverCol < totalCols && pnf.boxDates) {
      const col = pnf.columns[hoverCol];
      const colDates = pnf.boxDates[hoverCol];
      let matchIdx = -1;
      for (let bi = 0; bi < col.length; bi++) {
        if (rowInfo.priceToRow(col[bi]) === hoverRow) { matchIdx = bi; break; }
      }
      if (matchIdx >= 0 && colDates && colDates[matchIdx]) {
        const targetDate = colDates[matchIdx];
        const indices = [], prices = [];
        for (let bi = 0; bi < col.length; bi++) {
          if (colDates[bi] === targetDate) { indices.push(bi); prices.push(col[bi]); }
        }
        hoverBoxInfo = {
          date: targetDate,
          indices: indices,
          prices: prices,
          dir: pnf.columnDirections[hoverCol],
          hoveredIdx: matchIdx
        };
      }
    }
  }

  // --- Highlight same-date boxes ---
  if (hoverBoxInfo) {
    const col = pnf.columns[hoverCol];
    const isUp = hoverBoxInfo.dir === 'up';
    for (let k = 0; k < hoverBoxInfo.indices.length; k++) {
      const bi = hoverBoxInfo.indices[k];
      const price = col[bi];
      const row = rowInfo.priceToRow(price);
      const bx = w2sx(hoverCol);
      const by = w2sy(row);
      const opacity = (bi === hoverBoxInfo.hoveredIdx) ? 0.35 : 0.18;
      ctx.fillStyle = isUp
        ? 'rgba(38,166,154,' + opacity + ')'
        : 'rgba(239,83,80,' + opacity + ')';
      ctx.fillRect(bx, by, CW, RH);
    }
  }

  // --- X's and O's ---
  const symSize = Math.min(CW, RH);
  const half = symSize * 0.36;
  const lineW = Math.max(1, Math.min(2.5, zoom * 1.5));

  const visStartCol = Math.max(0, Math.floor(s2wCol(cL)) - 1);
  const visEndCol = Math.min(totalCols - 1, Math.ceil(s2wCol(cR)) + 1);

  for (let ci = visStartCol; ci <= visEndCol; ci++) {
    const col = pnf.columns[ci];
    const dir = pnf.columnDirections[ci];
    const isUp = dir === 'up';
    ctx.strokeStyle = isUp ? COLORS.up : COLORS.down;
    ctx.lineWidth = lineW;

    for (let bi = 0; bi < col.length; bi++) {
      const price = col[bi];
      const row = rowInfo.priceToRow(price);
      const cx = w2sx(ci) + CW / 2;
      const cy = w2sy(row) + RH / 2;
      if (cy < cT - RH || cy > cB + RH) continue;
      if (cx < cL - CW || cx > cR + CW) continue;

      if (isUp) {
        ctx.beginPath();
        ctx.moveTo(cx - half, cy - half); ctx.lineTo(cx + half, cy + half);
        ctx.moveTo(cx + half, cy - half); ctx.lineTo(cx - half, cy + half);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(cx, cy, half, 0, 2 * Math.PI);
        ctx.stroke();
      }
    }
  }

  // --- Crosshair (clipped) ---
  if (inChart && !isDragging) {
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = COLORS.crosshair;
    ctx.lineWidth = 1;
    const chy = w2sy(hoverRow) + RH / 2;
    ctx.beginPath(); ctx.moveTo(cL, chy); ctx.lineTo(cR, chy); ctx.stroke();
    const chx = w2sx(hoverCol) + CW / 2;
    ctx.beginPath(); ctx.moveTo(chx, cT); ctx.lineTo(chx, cB); ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.restore(); // end chart clip

  // --- Axis labels ---
  // Right price axis
  ctx.fillStyle = COLORS.textDim;
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  for (let r = rowInfo.minRow; r <= rowInfo.maxRow; r++) {
    if (r % rowStep !== 0) continue;
    const y = w2sy(r) + RH / 2;
    if (y < cT - 5 || y > cB + 5) continue;
    const pr = rowInfo.rowToPrice(r);
    ctx.fillText(fmtPrice(pr), cR + 6, y);
  }

  // Bottom date axis
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const dateStep = Math.max(1, Math.ceil(60 / CW));
  for (let c = 0; c < totalCols; c += dateStep) {
    const x = w2sx(c) + CW / 2;
    if (x < cL - 20 || x > cR + 20) continue;
    const d = pnf.columnDates[c];
    if (d) {
      ctx.fillStyle = COLORS.textDim;
      ctx.fillText(fmtDateShort(d), x, cB + 4);
    }
  }

  // --- Crosshair labels ---
  if (inChart && !isDragging) {
    // Price label on right axis
    const chy = w2sy(hoverRow) + RH / 2;
    const labelH = 18;
    ctx.fillStyle = COLORS.crossLabel;
    ctx.fillRect(cR, chy - labelH/2, MARGIN.right, labelH);
    ctx.fillStyle = '#fff';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(fmtPrice(hoverPrice), cR + MARGIN.right / 2, chy);

    // Date label on bottom axis
    if (hoverCol >= 0 && hoverCol < totalCols) {
      const chx = w2sx(hoverCol) + CW / 2;
      const d = pnf.columnDates[hoverCol];
      if (d) {
        const txt = d;
        ctx.font = '11px sans-serif';
        const tw = ctx.measureText(txt).width + 12;
        ctx.fillStyle = COLORS.crossLabel;
        ctx.fillRect(chx - tw/2, cB, tw, MARGIN.bottom);
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(txt, chx, cB + 4);
      }
    }
  }

  // --- Axis border lines ---
  ctx.strokeStyle = '#2a2e39';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cR, cT); ctx.lineTo(cR, cB); // right edge
  ctx.moveTo(cL, cB); ctx.lineTo(cR, cB); // bottom edge
  ctx.stroke();

  // --- Info overlay ---
  drawInfoOverlay(cL, cT);

  // --- Box hover tooltip ---
  if (hoverBoxInfo) {
    const tipFont = '12px sans-serif';
    const tipFontSm = '11px sans-serif';
    const pad = 10;
    const lineH = 18;
    const dateTxt = fmtDateLong(hoverBoxInfo.date);
    const boxCount = hoverBoxInfo.prices.length;
    const countTxt = boxCount + (boxCount === 1 ? ' box filled' : ' boxes filled');
    const pSorted = hoverBoxInfo.prices.slice().sort((a,b) => a - b);
    const pLow = pSorted[0], pHigh = pSorted[pSorted.length - 1];
    const arrow = hoverBoxInfo.dir === 'up' ? '\u2191' : '\u2193';
    const rangeTxt = boxCount > 1
      ? fmtPrice(pLow) + ' ' + arrow + ' ' + fmtPrice(pHigh)
      : fmtPrice(pLow);

    ctx.font = tipFont;
    const w1 = ctx.measureText(dateTxt).width;
    ctx.font = tipFontSm;
    const w2 = ctx.measureText(countTxt).width;
    const w3 = ctx.measureText(rangeTxt).width;
    const tipW = Math.max(w1, w2, w3) + pad * 2;
    const tipH = pad + lineH * 3 + pad - 6;

    let tipX = mouseX + 16;
    let tipY = mouseY - tipH / 2;
    if (tipX + tipW > canvasW - 4) tipX = mouseX - tipW - 16;
    if (tipY < 4) tipY = 4;
    if (tipY + tipH > canvasH - 4) tipY = canvasH - tipH - 4;

    drawRoundRect(tipX, tipY, tipW, tipH, 4);
    ctx.fillStyle = 'rgba(19,23,34,0.93)';
    ctx.fill();
    ctx.strokeStyle = '#363a45';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    let ty = tipY + pad;
    ctx.font = tipFont;
    ctx.fillStyle = '#d1d4dc';
    ctx.fillText(dateTxt, tipX + pad, ty);
    ty += lineH;
    ctx.font = tipFontSm;
    ctx.fillStyle = '#787b86';
    ctx.fillText(countTxt, tipX + pad, ty);
    ty += lineH;
    ctx.fillText(rangeTxt, tipX + pad, ty);
  }

  // --- Status bar ---
  updateStatusBar(hoverCol, hoverRow, hoverPrice, inChart);
}

function drawInfoOverlay(x, y) {
  const pad = 8;
  x += pad; y += pad;
  const bs = parseFloat(document.getElementById('box-size-select').value);
  const rs = parseInt(document.getElementById('reversal-select').value);
  const line1 = currentTicker + '  \u00B7  ' + fmtPrice(lastClose);
  const line2 = 'PnF ' + (bs*100).toFixed(2) + '% \u00D7 ' + rs +
    '  \u00B7  ' + pnf.columns.length + ' cols';
  const dateRange = pnf.columnDates[0] + ' \u2013 ' + pnf.columnDates[pnf.columnDates.length-1];
  const line3 = dateRange;

  // Semi-transparent backdrop
  ctx.font = '13px sans-serif';
  const w1 = ctx.measureText(line1).width;
  ctx.font = '11px sans-serif';
  const w2 = ctx.measureText(line2).width;
  const w3 = ctx.measureText(line3).width;
  const bw = Math.max(w1, w2, w3) + 12;
  ctx.fillStyle = 'rgba(19,23,34,0.75)';
  ctx.fillRect(x - 4, y - 2, bw, 50);

  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.font = '13px sans-serif';
  ctx.fillStyle = COLORS.text;
  ctx.fillText(line1, x, y);
  ctx.fillStyle = COLORS.textDim;
  ctx.font = '11px sans-serif';
  ctx.fillText(line2, x, y + 18);
  ctx.fillText(line3, x, y + 32);
}

function updateStatusBar(hCol, hRow, hPrice, inChart) {
  const sbInfo = document.getElementById('sb-info');
  const sbHover = document.getElementById('sb-hover');
  if (!pnf) { sbInfo.textContent = 'Enter a ticker and click Load'; sbHover.textContent = ''; return; }
  sbInfo.innerHTML = currentTicker + ' &middot; ' + pnf.columns.length + ' columns';
  if (inChart && hCol >= 0 && hCol < pnf.columns.length && !isDragging) {
    const dir = pnf.columnDirections[hCol];
    const boxes = pnf.columns[hCol].length;
    const date = pnf.columnDates[hCol] || '';
    sbHover.innerHTML = 'Col ' + hCol + ' (' +
      '<span class="val" style="color:' + (dir==='up'?COLORS.up:COLORS.down) + '">' + dir.toUpperCase() + '</span>' +
      ') &middot; ' + date + ' &middot; Price: <span class="val">' + fmtPrice(hPrice) + '</span>' +
      ' &middot; Boxes: <span class="val">' + boxes + '</span>';
  } else {
    sbHover.textContent = '';
  }
}

// ============================== FORMATTING ==============================
function fmtPrice(p) {
  if (p >= 100000) return p.toFixed(0);
  if (p >= 1000) return p.toFixed(1);
  if (p >= 10) return p.toFixed(2);
  if (p >= 1) return p.toFixed(3);
  if (p >= 0.01) return p.toFixed(4);
  return p.toFixed(6);
}
function fmtDateShort(d) {
  if (!d) return '';
  const parts = d.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return months[parseInt(parts[1])-1] + " '" + parts[0].slice(2);
}
function fmtDateLong(d) {
  if (!d) return '';
  const parts = d.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return months[parseInt(parts[1])-1] + ' ' + parseInt(parts[2]) + ', ' + parts[0];
}
function drawRoundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// ============================== VIEW CONTROL ==============================
function autoFit() {
  if (!pnf || !rowInfo) return;
  const cW = chartW(), cH = chartH();
  const totalCols = pnf.columns.length;
  const totalRows = rowInfo.maxRow - rowInfo.minRow + 1;
  if (totalCols === 0 || totalRows === 0) return;

  const zx = cW / (totalCols * BASE_CW);
  const zy = cH / (totalRows * BASE_RH);
  zoom = Math.min(zx, zy) * 0.92;
  zoom = Math.max(0.02, zoom);

  const CW = cw(), RH = rh();
  panX = chartLeft() + (cW - totalCols * CW) / 2;
  panY = chartTop() + (cH - totalRows * RH) / 2;
  render();
}

// ============================== INTERACTION ==============================
function onMouseDown(e) {
  if (e.button !== 0) return;
  isDragging = true;
  dragStartX = e.clientX; dragStartY = e.clientY;
  panStartX = panX; panStartY = panY;
  canvas.style.cursor = 'grabbing';
}
function onMouseMove(e) {
  const rect = canvas.getBoundingClientRect();
  mouseX = e.clientX - rect.left;
  mouseY = e.clientY - rect.top;
  if (isDragging) {
    panX = panStartX + (e.clientX - dragStartX);
    panY = panStartY + (e.clientY - dragStartY);
  }
  requestRender();
}
function onMouseUp(e) {
  isDragging = false;
  canvas.style.cursor = 'crosshair';
}
function onMouseLeave(e) {
  isDragging = false;
  mouseX = -1; mouseY = -1;
  canvas.style.cursor = 'crosshair';
  requestRender();
}
function onWheel(e) {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const oldZoom = zoom;
  // Continuous zoom: scales proportionally to deltaY for smooth trackpad support
  const factor = Math.pow(2, -e.deltaY * 0.004);
  zoom = Math.max(0.015, Math.min(zoom * factor, 40));
  const scale = zoom / oldZoom;
  panX = mx - (mx - panX) * scale;
  panY = my - (my - panY) * scale;
  requestRender();
}
function onKeyDown(e) {
  if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT') return;
  const PAN_STEP = 40;
  switch (e.key) {
    case 'r': case 'R': autoFit(); break;
    case 'ArrowLeft': panX += PAN_STEP; requestRender(); break;
    case 'ArrowRight': panX -= PAN_STEP; requestRender(); break;
    case 'ArrowUp': panY += PAN_STEP; requestRender(); break;
    case 'ArrowDown': panY -= PAN_STEP; requestRender(); break;
    case '+': case '=': zoom = Math.min(zoom * 1.15, 40); requestRender(); break;
    case '-': case '_': zoom = Math.max(zoom / 1.15, 0.015); requestRender(); break;
    case 'Home': panToStart(); break;
    case 'End': panToEnd(); break;
  }
}
function panToStart() {
  if (!pnf) return;
  panX = chartLeft() + 20;
  requestRender();
}
function panToEnd() {
  if (!pnf) return;
  panX = chartRight() - pnf.columns.length * cw() - 20;
  requestRender();
}

let renderRAF = null;
function requestRender() {
  if (renderRAF) return;
  renderRAF = requestAnimationFrame(() => { renderRAF = null; render(); });
}

// ============================== DATA LOADING ==============================
async function loadData(ticker, opts) {
  if (!ticker) return;
  isLoading = true;
  document.getElementById('loading-overlay').classList.remove('hidden');
  document.getElementById('load-btn').disabled = true;
  document.getElementById('load-btn').textContent = 'Loading\u2026';

  let url = '/api/ohlc?ticker=' + encodeURIComponent(ticker);
  if (opts.period) url += '&period=' + opts.period;
  if (opts.start) url += '&start=' + opts.start;
  if (opts.end) url += '&end=' + opts.end;

  try {
    const resp = await fetch(url);
    const json = await resp.json();
    if (json.error) { alert('Error: ' + json.error); return; }
    ohlcData = json.data;
    currentTicker = json.ticker;
    if (ohlcData.length > 0) lastClose = ohlcData[ohlcData.length - 1].close;
    // Sync sidebar highlight
    document.querySelectorAll('.sb-item.active').forEach(e => e.classList.remove('active'));
    document.querySelectorAll('.sb-item[data-ticker]').forEach(el => {
      if (normalizeTicker(el.dataset.ticker) === currentTicker) el.classList.add('active');
    });
    // Restore per-ticker settings (default to 1% x 3 if none saved)
    const boxSel = document.getElementById('box-size-select');
    const revSel = document.getElementById('reversal-select');
    const saved = getTickerSettings(currentTicker);
    const boxOptions = Array.from(boxSel.options).map(o => o.value);
    const revOptions = Array.from(revSel.options).map(o => o.value);
    if (saved.boxSize && boxOptions.indexOf(saved.boxSize) >= 0) {
      boxSel.value = saved.boxSize;
    } else {
      boxSel.value = '0.01';
    }
    revSel.value = saved.reversal && revOptions.indexOf(saved.reversal) >= 0 ? saved.reversal : '3';
    recalcPnF();
  } catch (err) {
    alert('Fetch error: ' + err.message);
  } finally {
    isLoading = false;
    document.getElementById('loading-overlay').classList.add('hidden');
    document.getElementById('load-btn').disabled = false;
    document.getElementById('load-btn').textContent = 'Load';
  }
}

function recalcPnF() {
  if (ohlcData.length === 0) return;
  const bs = parseFloat(document.getElementById('box-size-select').value);
  const rs = parseInt(document.getElementById('reversal-select').value);
  pnf = pruneEmptyColumns(generatePnF(ohlcData, bs, rs));
  if (pnf) {
    rowInfo = computeRowInfo(pnf, bs);
  }
  if (currentTicker) {
    activityByTicker[currentTicker] = analyzeDailyActivity(ohlcData, currentTicker);
    buildSidebar();
  }
  autoFit();
}

// ============================== CANVAS RESIZE ==============================
function resizeCanvas() {
  const container = document.getElementById('chart-container');
  const rect = container.getBoundingClientRect();
  dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  canvas.style.width = rect.width + 'px';
  canvas.style.height = rect.height + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  canvasW = rect.width;
  canvasH = rect.height;
}

// ============================== UI SETUP ==============================
function setupUI() {
  // Load button / Enter key
  document.getElementById('load-btn').addEventListener('click', () => {
    const t = document.getElementById('ticker-input').value.trim();
    const startVal = document.getElementById('start-date').value;
    const endVal = document.getElementById('end-date').value;
    if (startVal || endVal) {
      activePeriod = '';
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      loadData(t, { start: startVal || undefined, end: endVal || undefined });
    } else {
      loadData(t, { period: activePeriod || '2y' });
    }
  });
  document.getElementById('ticker-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('load-btn').click();
  });

  // Box size / reversal change → recalc
  document.getElementById('box-size-select').addEventListener('change', () => {
    saveCurrentTickerSettings();
    recalcPnF();
  });
  document.getElementById('reversal-select').addEventListener('change', () => {
    saveCurrentTickerSettings();
    recalcPnF();
  });

  // Period presets
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activePeriod = btn.dataset.period;
      document.getElementById('start-date').value = '';
      document.getElementById('end-date').value = '';
      const t = document.getElementById('ticker-input').value.trim();
      if (t) loadData(t, { period: activePeriod });
    });
  });

  // Reset view
  document.getElementById('reset-btn').addEventListener('click', autoFit);
  document.getElementById('add-watchlist-btn').addEventListener('click', addCurrentTickerToWatchlist);

  // Canvas events
  canvas.addEventListener('mousedown', onMouseDown);
  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseup', onMouseUp);
  canvas.addEventListener('mouseleave', onMouseLeave);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('dblclick', autoFit);
  document.addEventListener('keydown', onKeyDown);

  // Resize
  window.addEventListener('resize', () => {
    resizeCanvas();
    render();
  });

  canvas.style.cursor = 'crosshair';
}

// ============================== SIDEBAR ==============================
const SIDEBAR_DATA = [
  { cat: 'Index ETFs', items: [
    ['SPY','S&P 500'],['QQQ','Nasdaq 100'],['DIA','Dow 30'],['IWM','Russell 2000'],
    ['VTI','Total Market'],['EFA','Intl Dev'],['EEM','Emerging Mkts'],
    ['GLD','Gold'],['SLV','Silver'],['TLT','20Y+ Treasury'],['IEF','7-10Y Treasury'],
    ['HYG','High Yield'],['LQD','Inv Grade Corp'],['USO','Crude Oil'],['UNG','Nat Gas'],
    ['DBA','Agriculture'],['FXI','China'],['EWJ','Japan'],['EWZ','Brazil']]},
  { cat: 'Sector ETFs', items: [
    ['XLK','Technology'],['XLF','Financials'],['XLE','Energy'],['XLV','Healthcare'],
    ['XLI','Industrials'],['XLP','Cons Staples'],['XLY','Cons Discret'],['XLU','Utilities'],
    ['XLB','Materials'],['XLRE','Real Estate'],['XLC','Comm Svcs'],
    ['SMH','Semiconductors'],['XBI','Biotech'],['KRE','Reg Banks'],['XHB','Homebuilders'],
    ['ARKK','ARK Innov']]},
  { cat: 'Futures', items: [
    ['ES=F','S&P 500'],['NQ=F','Nasdaq 100'],['YM=F','Dow 30'],['RTY=F','Russell 2000'],
    ['CL=F','Crude Oil'],['GC=F','Gold'],['SI=F','Silver'],['HG=F','Copper'],
    ['NG=F','Nat Gas'],['ZB=F','30Y Bond'],['ZN=F','10Y Note'],
    ['ZC=F','Corn'],['ZS=F','Soybeans'],['ZW=F','Wheat'],
    ['6E=F','Euro FX'],['6J=F','Yen FX'],['BTC=F','Bitcoin']]},
  { cat: 'Crypto', items: [
    ['BTC-USD','Bitcoin'],['ETH-USD','Ethereum'],['SOL-USD','Solana'],
    ['XRP-USD','Ripple'],['ADA-USD','Cardano'],['DOGE-USD','Dogecoin']]},
  { cat: 'Stocks', sub: {
    'Mega Cap Tech': [
      ['AAPL','Apple'],['MSFT','Microsoft'],['GOOGL','Alphabet'],['AMZN','Amazon'],
      ['META','Meta'],['NVDA','Nvidia'],['TSLA','Tesla'],['TSM','TSMC']],
    'Semis & Hardware': [
      ['AVGO','Broadcom'],['AMD','AMD'],['QCOM','Qualcomm'],['TXN','Texas Inst'],
      ['AMAT','Applied Matls'],['MU','Micron'],['INTC','Intel'],['MRVL','Marvell'],
      ['KLAC','KLA Corp'],['LRCX','Lam Research'],['ADI','Analog Devices']],
    'Software & Cloud': [
      ['ORCL','Oracle'],['CRM','Salesforce'],['ADBE','Adobe'],['NOW','ServiceNow'],
      ['SNOW','Snowflake'],['PLTR','Palantir'],['NET','Cloudflare'],['PANW','Palo Alto'],
      ['CRWD','CrowdStrike'],['DDOG','Datadog'],['ZS','Zscaler'],
      ['SHOP','Shopify'],['SQ','Block']],
    'Internet & Media': [
      ['NFLX','Netflix'],['DIS','Disney'],['CMCSA','Comcast'],['UBER','Uber'],
      ['ABNB','Airbnb'],['SNAP','Snap'],['PINS','Pinterest'],['SPOT','Spotify'],
      ['COIN','Coinbase'],['RBLX','Roblox'],['TTWO','Take-Two']],
    'Financials': [
      ['JPM','JPMorgan'],['BAC','BofA'],['GS','Goldman'],['MS','Morgan Stan'],
      ['WFC','Wells Fargo'],['C','Citigroup'],['BLK','BlackRock'],['SCHW','Schwab'],
      ['AXP','Amex'],['V','Visa'],['MA','Mastercard'],['PYPL','PayPal'],
      ['COF','Capital One'],['BRK-B','Berkshire']],
    'Healthcare': [
      ['UNH','UnitedHealth'],['JNJ','J&J'],['LLY','Eli Lilly'],['PFE','Pfizer'],
      ['MRK','Merck'],['ABBV','AbbVie'],['TMO','Thermo Fisher'],['ABT','Abbott'],
      ['DHR','Danaher'],['BMY','Bristol-Myers'],['AMGN','Amgen'],['GILD','Gilead'],
      ['ISRG','Intuitive Surg'],['MDT','Medtronic']],
    'Energy': [
      ['XOM','Exxon'],['CVX','Chevron'],['COP','ConocoPhillips'],['SLB','Schlumberger'],
      ['EOG','EOG Res'],['OXY','Occidental'],['MPC','Marathon Petro'],['VLO','Valero'],
      ['PSX','Phillips 66']],
    'Industrials': [
      ['CAT','Caterpillar'],['BA','Boeing'],['HON','Honeywell'],['GE','GE Aero'],
      ['UNP','Union Pacific'],['RTX','RTX'],['DE','Deere'],['LMT','Lockheed'],
      ['UPS','UPS'],['FDX','FedEx'],['MMM','3M']],
    'Consumer & Retail': [
      ['WMT','Walmart'],['COST','Costco'],['HD','Home Depot'],['LOW','Lowes'],
      ['TGT','Target'],['MCD','McDonalds'],['SBUX','Starbucks'],['NKE','Nike'],
      ['PG','Procter&Gamble'],['KO','Coca-Cola'],['PEP','PepsiCo'],
      ['PM','Philip Morris'],['CL','Colgate'],['EL','Estee Lauder']],
    'Telecom & RE': [
      ['T','AT&T'],['VZ','Verizon'],['TMUS','T-Mobile'],
      ['AMT','Amer Tower'],['PLD','Prologis'],['CCI','Crown Castle'],['EQIX','Equinix'],
      ['O','Realty Income']]
  }}
];

function buildSidebar() {
  const sb = document.getElementById('sidebar');
  let html = '';
  const selected = getWatchlist(selectedWatchlistId);

  html += '<div class="wl-panel">';
  html += '<div class="wl-head"><span>Watchlists</span><button onclick="createWatchlist()" title="Create watchlist">+</button></div>';
  html += '<div class="wl-tabs">';
  for (const wl of appSettings.watchlists) {
    html += '<button class="wl-tab' + (wl.id === selected.id ? ' active' : '') + '" onclick="selectWatchlist(\'' +
      escapeHtml(wl.id) + '\')">' + escapeHtml(wl.name) + '</button>';
  }
  html += '</div>';
  html += '<div class="wl-actions">';
  html += '<button onclick="addCurrentTickerToWatchlist()">Add Current</button>';
  html += '<button onclick="refreshSelectedWatchlistActivity()">Scan</button>';
  if (!selected.readonly) {
    html += '<button onclick="renameWatchlist()">Rename</button><button onclick="deleteWatchlist()">Delete</button>';
  }
  html += '</div>';
  html += '<div class="wl-meta">' + escapeHtml(selected.symbols.length) + ' symbols';
  const pendingCount = selected.symbols.filter(t => activityByTicker[normalizeTicker(t)] === 'pending').length;
  if (pendingCount) html += ' · scanning ' + pendingCount;
  html += '</div>';
  for (const ticker of selected.symbols) {
    const tk = normalizeTicker(ticker);
    const i = selected.symbols.indexOf(ticker);
    html += '<div class="sb-item wl-symbol' + (selected.readonly ? '' : ' wl-editable') + '" data-ticker="' + escapeHtml(tk) + '" data-watchlist-index="' + i + '"' +
      (selected.readonly ? '' : ' draggable="true" ondragstart="onWatchlistDragStart(event)" ondragover="onWatchlistDragOver(event)" ondragleave="onWatchlistDragLeave(event)" ondrop="onWatchlistDrop(event)" ondragend="onWatchlistDragEnd(event)"') +
      ' onclick="clickTicker(this)">' +
      '<span class="tk">' + escapeHtml(tk) + '</span><span class="desc"></span>';
    if (selected.readonly) {
      html += activityBadgeHtml(tk);
    } else {
      html += '<button class="remove-symbol" onclick="removeTickerFromWatchlist(event,\'' +
        escapeHtml(tk) + '\')" title="Remove">×</button>' + activityBadgeHtml(tk);
    }
    html += '</div>';
  }
  html += '</div>';
  html += '<div class="sb-library-title">Symbol Library</div>';

  for (const sec of SIDEBAR_DATA) {
    const catId = sec.cat;
    html += '<div class="sb-cat' + (collapsedCats.has(catId) ? ' collapsed' : '') + '" data-cat="' + escapeHtml(catId) + '">';
    html += '<div class="sb-cat-hdr" onclick="toggleCat(this)">' +
      sec.cat + '<span class="arrow">&#9660;</span></div>';
    html += '<div class="sb-cat-body">';
    if (sec.items) {
      for (const t of sec.items) {
        html += '<div class="sb-item" data-ticker="'+t[0]+'" onclick="clickTicker(this)">' +
          '<span class="tk">'+t[0]+'</span><span class="desc">'+t[1]+'</span>' + activityBadgeHtml(t[0]) + '</div>';
      }
    }
    if (sec.sub) {
      for (const [subName, tickers] of Object.entries(sec.sub)) {
        html += '<div class="sb-sub">' + subName + '</div>';
        for (const t of tickers) {
          html += '<div class="sb-item" data-ticker="'+t[0]+'" onclick="clickTicker(this)">' +
            '<span class="tk">'+t[0]+'</span><span class="desc">'+t[1]+'</span>' + activityBadgeHtml(t[0]) + '</div>';
        }
      }
    }
    html += '</div></div>';
  }
  sb.innerHTML = html;
  if (currentTicker) {
    document.querySelectorAll('.sb-item[data-ticker]').forEach(el => {
      if (normalizeTicker(el.dataset.ticker) === currentTicker) el.classList.add('active');
    });
  }
}

function activityBadgeHtml(ticker) {
  const activity = activityByTicker[normalizeTicker(ticker)];
  if (activity === 'pending') {
    return '<span class="activity-badge pending" title="Scanning">…</span>';
  }
  if (!activity) return '<span class="activity-badge" title="No scanned activity today">-</span>';
  return '<span class="activity-badge ' + activity.className + '" title="' +
    escapeHtml(activity.title) + '">' + escapeHtml(activity.label) + '</span>';
}

function selectWatchlist(id) {
  selectedWatchlistId = id;
  buildSidebar();
  refreshSelectedWatchlistActivity();
}

function createWatchlist() {
  const name = prompt('Watchlist name');
  if (!name || !name.trim()) return;
  const id = 'wl-' + Date.now().toString(36);
  appSettings.watchlists.push({ id, name: name.trim(), symbols: [], readonly: false });
  selectedWatchlistId = id;
  saveSettings();
  buildSidebar();
}

function renameWatchlist() {
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || wl.readonly) return;
  const name = prompt('Watchlist name', wl.name);
  if (!name || !name.trim()) return;
  wl.name = name.trim();
  saveSettings();
  buildSidebar();
}

function deleteWatchlist() {
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || wl.readonly) return;
  if (!confirm('Delete "' + wl.name + '"?')) return;
  appSettings.watchlists = appSettings.watchlists.filter(w => w.id !== wl.id);
  selectedWatchlistId = 'default';
  saveSettings();
  buildSidebar();
}

function addCurrentTickerToWatchlist() {
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || wl.readonly) {
    alert('Create or select a custom watchlist first.');
    return;
  }
  const ticker = normalizeTicker(document.getElementById('ticker-input').value || currentTicker);
  if (!ticker) return;
  if (!wl.symbols.map(normalizeTicker).includes(ticker)) wl.symbols.push(ticker);
  saveSettings();
  buildSidebar();
  refreshSelectedWatchlistActivity();
}

function removeTickerFromWatchlist(event, ticker) {
  event.stopPropagation();
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || wl.readonly) return;
  wl.symbols = wl.symbols.filter(t => normalizeTicker(t) !== normalizeTicker(ticker));
  saveSettings();
  buildSidebar();
}

function onWatchlistDragStart(event) {
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || wl.readonly) return;
  draggedWatchlistIndex = parseInt(event.currentTarget.dataset.watchlistIndex, 10);
  event.currentTarget.classList.add('dragging');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', String(draggedWatchlistIndex));
}

function onWatchlistDragOver(event) {
  if (draggedWatchlistIndex === null) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  event.currentTarget.classList.add('drag-over');
}

function onWatchlistDragLeave(event) {
  event.currentTarget.classList.remove('drag-over');
}

function onWatchlistDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || wl.readonly || draggedWatchlistIndex === null) return;
  const targetIndex = parseInt(event.currentTarget.dataset.watchlistIndex, 10);
  if (!Number.isInteger(targetIndex) || targetIndex === draggedWatchlistIndex) {
    onWatchlistDragEnd(event);
    return;
  }
  const symbols = wl.symbols.slice();
  const moved = symbols.splice(draggedWatchlistIndex, 1)[0];
  symbols.splice(targetIndex, 0, moved);
  wl.symbols = symbols;
  draggedWatchlistIndex = null;
  suppressTickerClickUntil = Date.now() + 250;
  saveSettings();
  buildSidebar();
}

function onWatchlistDragEnd(event) {
  draggedWatchlistIndex = null;
  suppressTickerClickUntil = Date.now() + 250;
  document.querySelectorAll('.wl-symbol.dragging,.wl-symbol.drag-over').forEach(el => {
    el.classList.remove('dragging', 'drag-over');
  });
}

function refreshSelectedWatchlistActivity() {
  const wl = getWatchlist(selectedWatchlistId);
  if (!wl || !wl.symbols.length) return;
  refreshWatchlistActivity(wl.symbols);
}

async function refreshWatchlistActivity(symbols) {
  const token = ++activityScanToken;
  const uniqueSymbols = Array.from(new Set(symbols.map(normalizeTicker).filter(Boolean)));
  uniqueSymbols.forEach(t => { activityByTicker[t] = 'pending'; });
  buildSidebar();
  for (const ticker of uniqueSymbols) {
    if (token !== activityScanToken) return;
    try {
      const resp = await fetch('/api/ohlc?ticker=' + encodeURIComponent(ticker) + '&period=2y');
      const json = await resp.json();
      activityByTicker[ticker] = json.error ? null : analyzeDailyActivity(json.data, ticker);
    } catch(e) {
      activityByTicker[ticker] = null;
    }
    buildSidebar();
  }
}

function toggleCat(hdr) {
  const cat = hdr.parentElement.dataset.cat;
  hdr.parentElement.classList.toggle('collapsed');
  if (!cat) return;
  if (hdr.parentElement.classList.contains('collapsed')) {
    collapsedCats.add(cat);
  } else {
    collapsedCats.delete(cat);
  }
}

function clickTicker(el) {
  if (Date.now() < suppressTickerClickUntil) return;
  const ticker = el.dataset.ticker;
  document.getElementById('ticker-input').value = ticker;
  // Highlight active
  document.querySelectorAll('.sb-item.active').forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  // Load
  const startVal = document.getElementById('start-date').value;
  const endVal = document.getElementById('end-date').value;
  if (startVal || endVal) {
    loadData(ticker, { start: startVal || undefined, end: endVal || undefined });
  } else {
    loadData(ticker, { period: activePeriod || '2y' });
  }
}

Object.assign(window, {
  addCurrentTickerToWatchlist,
  clickTicker,
  createWatchlist,
  deleteWatchlist,
  onWatchlistDragEnd,
  onWatchlistDragLeave,
  onWatchlistDragOver,
  onWatchlistDragStart,
  onWatchlistDrop,
  refreshSelectedWatchlistActivity,
  removeTickerFromWatchlist,
  renameWatchlist,
  selectWatchlist,
  toggleCat,
});

// ============================== INIT ==============================
async function init() {
  await loadSettings();
  buildSidebar();
  resizeCanvas();
  setupUI();
  render();
  // Auto-load SPY on startup & highlight it
  loadData('SPY', { period: '2y' });
  refreshSelectedWatchlistActivity();
  const spyEl = document.querySelector('.sb-item[data-ticker="SPY"]');
  if (spyEl) spyEl.classList.add('active');
}

window.addEventListener('DOMContentLoaded', init);
