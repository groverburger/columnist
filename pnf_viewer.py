#!/usr/bin/env python3
"""
PnF Viewer - Interactive Point-and-Figure Chart Explorer

Usage:
    python pnf_viewer.py             # opens in native window (pywebview)
    python pnf_viewer.py --browser   # opens in default browser instead

Requirements:
    pip install yfinance pywebview
"""

import argparse
import json
import socket
import threading
import webbrowser
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Error: yfinance is required. Install with: pip install yfinance")
    sys.exit(1)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def fetch_ohlc(ticker, start=None, end=None, period=None):
    kwargs = {}
    if period:
        kwargs['period'] = period
    else:
        if start:
            kwargs['start'] = start
        if end:
            kwargs['end'] = end
        if not start and not end:
            kwargs['period'] = '2y'

    df = yf.download(ticker, **kwargs, progress=False, auto_adjust=True)

    if df.empty:
        return {'error': f'No data found for {ticker}'}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    needed = ['Open', 'High', 'Low', 'Close']
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return {'error': f'Missing columns: {missing}'}

    df = df[needed].dropna()
    result = []
    for idx, row in df.iterrows():
        result.append({
            'date': idx.strftime('%Y-%m-%d'),
            'open': round(float(row['Open']), 6),
            'high': round(float(row['High']), 6),
            'low': round(float(row['Low']), 6),
            'close': round(float(row['Close']), 6),
        })
    return {'data': result, 'ticker': ticker.upper()}


HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PnF Viewer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',sans-serif;
  background:#131722;color:#d1d4dc;overflow:hidden;height:100vh;display:flex;flex-direction:column;user-select:none}
#toolbar{display:flex;align-items:center;gap:8px;padding:6px 12px;background:#1e222d;
  border-bottom:1px solid #2a2e39;flex-shrink:0;flex-wrap:wrap}
#toolbar label{font-size:12px;color:#787b86}
#toolbar .sep{width:1px;height:24px;background:#2a2e39;margin:0 4px}
input,select{background:#2a2e39;border:1px solid #363a45;color:#d1d4dc;padding:5px 8px;
  border-radius:4px;font-size:13px;outline:none}
input:focus,select:focus{border-color:#2962ff}
#ticker-input{width:90px;text-transform:uppercase}
.date-input{width:120px}
button{cursor:pointer;background:#2a2e39;border:1px solid #363a45;color:#d1d4dc;
  padding:5px 10px;border-radius:4px;font-size:13px;outline:none;transition:background .15s}
button:hover{background:#363a45}
.btn-primary{background:#2962ff;border-color:#2962ff;color:#fff;font-weight:600}
.btn-primary:hover{background:#1e53e5}
.btn-primary:disabled{background:#2a2e39;border-color:#363a45;color:#787b86;cursor:default}
.preset-btn{padding:4px 8px;font-size:11px;color:#787b86;font-weight:500}
.preset-btn:hover,.preset-btn.active{color:#d1d4dc;background:#363a45}
#chart-container{flex:1;position:relative;overflow:hidden;background:#131722}
canvas{display:block;position:absolute;top:0;left:0}
#statusbar{padding:3px 12px;background:#1e222d;border-top:1px solid #2a2e39;
  font-size:11px;color:#787b86;flex-shrink:0;display:flex;gap:16px}
#statusbar .val{color:#d1d4dc}
#loading-overlay{position:absolute;top:0;left:0;right:0;bottom:0;
  background:rgba(19,23,34,0.85);display:flex;align-items:center;justify-content:center;
  font-size:15px;color:#787b86;z-index:10;pointer-events:none}
.hidden{display:none!important}
#main-area{flex:1;display:flex;overflow:hidden}
#sidebar{width:175px;background:#1e222d;border-right:1px solid #2a2e39;
  overflow-y:auto;flex-shrink:0;font-size:12px}
#sidebar::-webkit-scrollbar{width:5px}
#sidebar::-webkit-scrollbar-track{background:transparent}
#sidebar::-webkit-scrollbar-thumb{background:#363a45;border-radius:3px}
.sb-cat{border-bottom:1px solid #2a2e39}
.sb-cat-hdr{padding:6px 10px;font-size:10px;font-weight:700;color:#787b86;
  text-transform:uppercase;letter-spacing:.5px;cursor:pointer;display:flex;
  justify-content:space-between;align-items:center}
.sb-cat-hdr:hover{color:#d1d4dc}
.sb-cat-hdr .arrow{font-size:8px;transition:transform .15s}
.sb-cat.collapsed .sb-cat-body{display:none}
.sb-cat.collapsed .arrow{transform:rotate(-90deg)}
.sb-item{padding:3px 10px;cursor:pointer;display:flex;justify-content:space-between;
  align-items:center;color:#d1d4dc;transition:background .1s;font-size:12px}
.sb-item:hover{background:#2a2e39}
.sb-item.active{background:rgba(41,98,255,0.13);color:#5b8def}
.sb-item .tk{font-weight:500}
.sb-item .desc{color:#555b66;font-size:10px;text-align:right;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:80px}
.sb-sub{padding:5px 10px 2px;font-size:9px;font-weight:700;color:#4a4e59;
  text-transform:uppercase;letter-spacing:.3px}
</style>
</head>
<body>

<div id="toolbar">
  <input type="text" id="ticker-input" value="SPY" placeholder="Ticker" spellcheck="false">
  <button class="btn-primary" id="load-btn">Load</button>
  <div class="sep"></div>
  <label>Box%</label>
  <select id="box-size-select">
    <option value="0.0025">0.25%</option>
    <option value="0.005">0.50%</option>
    <option value="0.0075">0.75%</option>
    <option value="0.01" selected>1.00%</option>
    <option value="0.015">1.50%</option>
    <option value="0.02">2.00%</option>
    <option value="0.03">3.00%</option>
    <option value="0.05">5.00%</option>
  </select>
  <label>Rev</label>
  <select id="reversal-select">
    <option value="1">1</option>
    <option value="2">2</option>
    <option value="3" selected>3</option>
    <option value="4">4</option>
    <option value="5">5</option>
  </select>
  <div class="sep"></div>
  <button class="preset-btn" data-period="1y">1Y</button>
  <button class="preset-btn active" data-period="2y">2Y</button>
  <button class="preset-btn" data-period="3y">3Y</button>
  <button class="preset-btn" data-period="5y">5Y</button>
  <button class="preset-btn" data-period="10y">10Y</button>
  <button class="preset-btn" data-period="max">Max</button>
  <div class="sep"></div>
  <label>From</label>
  <input type="date" class="date-input" id="start-date">
  <label>To</label>
  <input type="date" class="date-input" id="end-date">
  <div class="sep"></div>
  <button id="reset-btn" title="Reset view (R)">Reset View</button>
</div>

<div id="main-area">
<div id="sidebar"></div>
<div id="chart-container">
  <canvas id="chart"></canvas>
  <div id="loading-overlay" class="hidden">Loading&hellip;</div>
</div>
</div>

<div id="statusbar">
  <span id="sb-info">Enter a ticker and click Load</span>
  <span id="sb-hover"></span>
</div>

<script>
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
let tickerBoxSizes = {};
try { tickerBoxSizes = JSON.parse(localStorage.getItem('pnfBoxSizes')) || {}; } catch(e) {}

const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');
let dpr = 1, canvasW = 0, canvasH = 0;

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
    const match = document.querySelector('.sb-item[data-ticker="'+currentTicker+'"]');
    if (match) match.classList.add('active');
    // Restore per-ticker box size (default to 1% if none saved)
    const sel = document.getElementById('box-size-select');
    const savedBs = tickerBoxSizes[currentTicker];
    const opts = Array.from(sel.options).map(o => o.value);
    if (savedBs && opts.indexOf(savedBs) >= 0) {
      sel.value = savedBs;
    } else {
      sel.value = '0.01';
    }
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
  pnf = generatePnF(ohlcData, bs, rs);
  if (pnf) {
    // Remove empty trailing columns
    while (pnf.columns.length > 0 && pnf.columns[pnf.columns.length-1].length === 0) {
      pnf.columns.pop(); pnf.boxDates.pop(); pnf.columnDates.pop(); pnf.columnDirections.pop();
    }
    rowInfo = computeRowInfo(pnf, bs);
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
    if (currentTicker) {
      tickerBoxSizes[currentTicker] = document.getElementById('box-size-select').value;
      try { localStorage.setItem('pnfBoxSizes', JSON.stringify(tickerBoxSizes)); } catch(e) {}
    }
    recalcPnF();
  });
  document.getElementById('reversal-select').addEventListener('change', recalcPnF);

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
  for (const sec of SIDEBAR_DATA) {
    html += '<div class="sb-cat">';
    html += '<div class="sb-cat-hdr" onclick="toggleCat(this)">' +
      sec.cat + '<span class="arrow">&#9660;</span></div>';
    html += '<div class="sb-cat-body">';
    if (sec.items) {
      for (const t of sec.items) {
        html += '<div class="sb-item" data-ticker="'+t[0]+'" onclick="clickTicker(this)">' +
          '<span class="tk">'+t[0]+'</span><span class="desc">'+t[1]+'</span></div>';
      }
    }
    if (sec.sub) {
      for (const [subName, tickers] of Object.entries(sec.sub)) {
        html += '<div class="sb-sub">' + subName + '</div>';
        for (const t of tickers) {
          html += '<div class="sb-item" data-ticker="'+t[0]+'" onclick="clickTicker(this)">' +
            '<span class="tk">'+t[0]+'</span><span class="desc">'+t[1]+'</span></div>';
        }
      }
    }
    html += '</div></div>';
  }
  sb.innerHTML = html;
}

function toggleCat(hdr) {
  hdr.parentElement.classList.toggle('collapsed');
}

function clickTicker(el) {
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

// ============================== INIT ==============================
function init() {
  buildSidebar();
  resizeCanvas();
  setupUI();
  render();
  // Auto-load SPY on startup & highlight it
  loadData('SPY', { period: '2y' });
  const spyEl = document.querySelector('.sb-item[data-ticker="SPY"]');
  if (spyEl) spyEl.classList.add('active');
}

window.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""


class PnFHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            body = HTML_CONTENT.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == '/api/ohlc':
            params = parse_qs(parsed.query)
            ticker = params.get('ticker', ['SPY'])[0].strip()
            start = params.get('start', [None])[0]
            end = params.get('end', [None])[0]
            period = params.get('period', [None])[0]
            try:
                result = fetch_ohlc(ticker, start=start, end=end, period=period)
            except Exception as e:
                result = {'error': str(e)}
            body = json.dumps(result).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    parser = argparse.ArgumentParser(description='PnF Viewer - Interactive Point-and-Figure Chart Explorer')
    parser.add_argument('--browser', action='store_true',
                        help='Open in default browser instead of native window')
    args = parser.parse_args()

    port = find_free_port()
    server = HTTPServer(('127.0.0.1', port), PnFHandler)
    url = f'http://127.0.0.1:{port}'

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f'PnF Viewer running at {url}')

    if args.browser:
        webbrowser.open(url)
        try:
            signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
            server.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        try:
            import webview
            webview.create_window('PnF Viewer', url, width=1400, height=900)
            webview.start()
        except ImportError:
            print('pywebview not found, falling back to browser (pip install pywebview)')
            webbrowser.open(url)
            try:
                signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
                server.serve_forever()
            except (KeyboardInterrupt, SystemExit):
                pass

    server.shutdown()


if __name__ == '__main__':
    main()
