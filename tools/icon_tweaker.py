#!/usr/bin/env python3
"""One-off live icon tweaker for the Columnist icon.

Run from the repo root:
    python3 tools/icon_tweaker.py

It opens a local browser UI with sliders and exports PNG files into
assets/icon-iterations/.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import base64
import json
import socket
import threading
import time
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "icon-iterations"


HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Columnist Icon Tweaker</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#10141f;color:#d9dee8;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:grid;grid-template-columns:360px 1fr;height:100vh;overflow:hidden}
aside{background:#181d2a;border-right:1px solid #2b3242;padding:14px;overflow:auto}
main{display:flex;align-items:center;justify-content:center;min-width:0}
h1{font-size:16px;margin:0 0 12px}
.row{display:grid;grid-template-columns:112px 1fr 52px;gap:8px;align-items:center;margin:8px 0}
label{color:#a8b0c0}
input[type=range]{width:100%}
input[type=text]{width:100%;background:#222838;border:1px solid #353e51;color:#d9dee8;border-radius:4px;padding:7px}
button{background:#273044;border:1px solid #3a455b;color:#e7ebf2;border-radius:4px;padding:7px 10px;cursor:pointer}
button:hover{background:#323c53}
.actions{display:flex;gap:8px;margin:12px 0}
.actions button{flex:1}
canvas{width:min(78vh,78vw);height:min(78vh,78vw);image-rendering:auto}
.hint{color:#778196;font-size:12px;line-height:1.35;margin-top:10px}
.group{border-top:1px solid #2b3242;margin-top:14px;padding-top:12px}
#status{color:#7bd3c9;min-height:18px}
</style>
</head>
<body>
<aside>
  <h1>Columnist Icon Tweaker</h1>
  <label>Pattern, top row first</label>
  <input id="pattern" type="text" value="    X|X X X|XOXOX|XOXOX|XO OX|X    ">
  <div class="hint">Use <code>|</code> between rows. X/O draw symbols; spaces are empty cells.</div>

  <div class="group" id="controls"></div>

  <div class="actions">
    <button id="reset">Reset</button>
    <button id="export">Export PNG</button>
  </div>
  <div id="status"></div>
  <div class="hint">Exports to <code>assets/icon-iterations/icon-tweaker-export.png</code>.</div>
</aside>
<main><canvas id="icon" width="1024" height="1024"></canvas></main>

<script>
const defaults = {
  left: 166, top: 164, cellX: 144, cellY: 106,
  graphScale: 100, glyph: 39, stroke: 16, xOffset: 56, yOffset: 36,
  tileMargin: 46, radius: 178,
  bgTop: 30, bgBottom: 11, bgLift: 15,
  gridAlpha: 138, highlight: 7, highlightHeight: 250,
  border: 205, innerShadow: 86
};
const defs = [
  ['left','Left',80,260,1], ['top','Top',80,260,1],
  ['graphScale','Graph Scale',70,135,1],
  ['cellX','Cell X',96,190,1], ['cellY','Cell Y',78,140,1],
  ['glyph','Glyph',24,52,1], ['stroke','Stroke',8,24,1],
  ['xOffset','X Offset',35,75,1], ['yOffset','Y Offset',20,55,1],
  ['tileMargin','Tile Margin',20,80,1], ['radius','Radius',120,220,1],
  ['bgTop','Top Bright',18,48,1], ['bgBottom','Bottom Bright',5,24,1],
  ['bgLift','Light Lift',0,28,1], ['gridAlpha','Grid Alpha',30,220,1],
  ['highlight','Highlight',0,22,1], ['highlightHeight','Highlight H',120,380,1],
  ['border','Border Alpha',60,255,1], ['innerShadow','Inner Shadow',0,150,1]
];
const controls = document.getElementById('controls');
for (const [key,label,min,max,step] of defs) {
  controls.insertAdjacentHTML('beforeend',
    `<div class="row"><label for="${key}">${label}</label><input id="${key}" type="range" min="${min}" max="${max}" step="${step}"><span id="${key}Val"></span></div>`);
}
const canvas = document.getElementById('icon');
const ctx = canvas.getContext('2d');
const patternInput = document.getElementById('pattern');
const statusEl = document.getElementById('status');

function setDefaults() {
  for (const [key] of defs) document.getElementById(key).value = defaults[key];
}
function values() {
  const v = {};
  for (const [key] of defs) {
    v[key] = Number(document.getElementById(key).value);
    document.getElementById(key + 'Val').textContent = v[key];
  }
  return v;
}
function rr(ctx,x,y,w,h,r) {
  ctx.beginPath();
  ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.quadraticCurveTo(x+w,y,x+w,y+r);
  ctx.lineTo(x+w,y+h-r); ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);
  ctx.lineTo(x+r,y+h); ctx.quadraticCurveTo(x,y+h,x,y+h-r);
  ctx.lineTo(x,y+r); ctx.quadraticCurveTo(x,y,x+r,y); ctx.closePath();
}
function line(a,b,c,d,color,w) {
  ctx.strokeStyle = color; ctx.lineWidth = w; ctx.lineCap = 'butt';
  ctx.beginPath(); ctx.moveTo(a,b); ctx.lineTo(c,d); ctx.stroke();
}
function drawX(cx, cy, v) {
  const h = v.glyph, w = v.stroke;
  line(cx-h, cy-h, cx+h, cy+h, '#26bcb2', w);
  line(cx+h, cy-h, cx-h, cy+h, '#26bcb2', w);
  line(cx-h+4, cy-h, cx+h-6, cy+h-9, 'rgba(111,230,222,.28)', 2);
}
function drawO(cx, cy, v) {
  const r = v.glyph + 1;
  ctx.strokeStyle = '#ff4e52'; ctx.lineWidth = v.stroke;
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,139,139,.33)'; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.arc(cx, cy, r, Math.PI*1.15, Math.PI*1.75); ctx.stroke();
}
function draw() {
  const v = values();
  const S = 1024;
  ctx.clearRect(0,0,S,S);
  const m = v.tileMargin, r = v.radius;
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,.44)'; ctx.shadowBlur = 28; ctx.shadowOffsetY = 18;
  rr(ctx,m,m,S-m*2,S-m*2,r); ctx.fillStyle = '#111827'; ctx.fill();
  ctx.restore();

  rr(ctx,m,m,S-m*2,S-m*2,r); ctx.clip();
  const grad = ctx.createLinearGradient(0,m,0,S-m);
  grad.addColorStop(0, `rgb(${v.bgTop},${v.bgTop+5},${v.bgTop+19})`);
  grad.addColorStop(1, `rgb(${v.bgBottom},${v.bgBottom+4},${v.bgBottom+15})`);
  ctx.fillStyle = grad; ctx.fillRect(0,0,S,S);
  const rad = ctx.createRadialGradient(m+180,m+110,10,m+180,m+110,520);
  rad.addColorStop(0, `rgba(255,255,255,${v.bgLift/255})`);
  rad.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = rad; ctx.fillRect(0,0,S,S);

  ctx.strokeStyle = `rgba(62,70,88,${v.border/255})`; ctx.lineWidth = 4; rr(ctx,m,m,S-m*2,S-m*2,r); ctx.stroke();
  ctx.strokeStyle = `rgba(0,0,0,${v.innerShadow/255})`; ctx.lineWidth = 3; rr(ctx,m+14,m+16,S-(m+14)*2,S-(m+16)*2,r-14); ctx.stroke();

  const rows = patternInput.value.split('|');
  const maxCols = Math.max(...rows.map(r=>r.length));
  const graphW = (maxCols - 1) * v.cellX + v.xOffset * 2;
  const graphH = (rows.length - 1) * v.cellY + v.yOffset * 2;
  const graphCx = v.left + graphW / 2;
  const graphCy = v.top + graphH / 2;
  const graphScale = v.graphScale / 100;
  function sx(x) { return graphCx + (x - graphCx) * graphScale; }
  function sy(y) { return graphCy + (y - graphCy) * graphScale; }
  const drawValues = Object.assign({}, v, {
    glyph: v.glyph * graphScale,
    stroke: v.stroke * graphScale
  });
  ctx.fillStyle = `rgba(51,59,77,${v.gridAlpha/255})`;
  for (let row=0; row<rows.length; row++) {
    for (let col=0; col<maxCols; col++) {
      const x = v.left + col*v.cellX;
      const y = v.top + row*v.cellY;
      ctx.beginPath(); ctx.arc(sx(x),sy(y),3*graphScale,0,Math.PI*2); ctx.fill();
    }
  }
  for (let row=0; row<rows.length; row++) {
    const line = rows[row];
    for (let col=0; col<line.length; col++) {
      const ch = line[col];
      const cx = v.left + col*v.cellX + v.xOffset;
      const cy = v.top + row*v.cellY + v.yOffset;
      if (ch === 'X') drawX(sx(cx), sy(cy), drawValues);
      if (ch === 'O') drawO(sx(cx), sy(cy), drawValues);
    }
  }
  const hg = ctx.createLinearGradient(0,m,0,m+v.highlightHeight);
  hg.addColorStop(0, `rgba(255,255,255,${v.highlight/255})`);
  hg.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = hg; rr(ctx,m+24,m+24,S-(m+24)*2,v.highlightHeight,r-24); ctx.fill();
  ctx.restore();
}
async function exportPng() {
  statusEl.textContent = 'Exporting...';
  const image = canvas.toDataURL('image/png');

  // Always trigger a browser download; the server save below is a convenience.
  const link = document.createElement('a');
  link.href = image;
  link.download = 'columnist-icon.png';
  document.body.appendChild(link);
  link.click();
  link.remove();

  try {
    const res = await fetch('/export', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ image, values: values(), pattern: patternInput.value })
    });
    const json = await res.json();
    statusEl.textContent = json.ok ? `Downloaded and saved ${json.path}` : `Downloaded; server save failed: ${json.error}`;
  } catch (err) {
    statusEl.textContent = `Downloaded; server save failed: ${err.message}`;
  }
}
setDefaults();
for (const [key] of defs) document.getElementById(key).addEventListener('input', draw);
patternInput.addEventListener('input', draw);
document.getElementById('reset').addEventListener('click', () => { setDefaults(); draw(); });
document.getElementById('export').addEventListener('click', exportPng);
draw();
</script>
</body>
</html>
"""


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/export":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            image_data = payload["image"].split(",", 1)[1]
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out = OUT_DIR / "icon-tweaker-export.png"
            out.write_bytes(base64.b64decode(image_data))
            meta = OUT_DIR / "icon-tweaker-export.json"
            meta.write_text(json.dumps({
                "values": payload.get("values", {}),
                "pattern": payload.get("pattern", ""),
                "exportedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, indent=2), encoding="utf-8")
            self.send_json({"ok": True, "path": str(out.relative_to(ROOT))})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = find_free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Icon tweaker running at {url}")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
