#!/usr/bin/env python3
"""Touch-draw on the flip-dot display from a phone browser.

Run this on a PC that can reach the display, then open the printed URL on your
phone (same WiFi). Draw with your finger; the frame is forwarded over UDP.
"Life" runs Conway's Game of Life on whatever is drawn, until pressed again or
the pattern stops changing. You can keep drawing while it runs. On an empty
display it first scatters a few well-known patterns to start from.
"""
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from display import DISPLAY_IP, UDP_PORT, display_size, stride

HTTP_PORT = 8000

# Set by main() from the display's geometry.
COLS = ROWS = FRAME_BYTES = 0
PAGE = ""

_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

PAGE_TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Flip-dot draw</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #0a0a0a;
    font-family: system-ui, sans-serif; position: fixed; width: 100%;
    -webkit-user-select: none; user-select: none; }
  #bar { height: 56px; display: flex; gap: 10px; align-items: center;
    justify-content: center; padding: 8px; box-sizing: border-box; }
  button { height: 40px; padding: 0 16px; border: 0; border-radius: 8px;
    font-size: 15px; font-weight: 600; color: #000; }
  #toggle.yellow { background: #f2c014; }
  #toggle.black { background: #555; color: #fff; }
  #clear { background: #2b2b2b; color: #ddd; }
  #life { background: #2b2b2b; color: #ddd; }
  #life.running { background: #3a7d44; color: #fff; }
  #wrap { display: flex; align-items: center; justify-content: center;
    height: calc(100% - 56px); }
  canvas { touch-action: none; background: #1a1a1a; border-radius: 6px; }
</style>
</head>
<body>
  <div id="bar">
    <button id="toggle" class="yellow">Drawing: YELLOW</button>
    <button id="clear">Clear</button>
    <button id="life">Life</button>
  </div>
  <div id="wrap"><canvas id="c"></canvas></div>
<script>
const COLS = __COLS__, ROWS = __ROWS__;
const STRIDE = (COLS + 7) >> 3;
const BG = "#1a1a1a", OFF = "#2b2b2b", YELLOW = "#f2c014";
const grid = new Uint8Array(COLS * ROWS);
let paintVal = 1, cell = 10;
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");

function layout() {
  const availW = window.innerWidth - 24;
  const availH = window.innerHeight - 56 - 24;
  cell = Math.max(4, Math.floor(Math.min(availW / COLS, availH / ROWS)));
  const w = cell * COLS, h = cell * ROWS;
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = w + "px"; canvas.style.height = h + "px";
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

function draw() {
  ctx.fillStyle = BG; ctx.fillRect(0, 0, cell * COLS, cell * ROWS);
  const r = cell * 0.42;
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    ctx.beginPath();
    ctx.arc(x * cell + cell / 2, y * cell + cell / 2, r, 0, 7);
    ctx.fillStyle = grid[y * COLS + x] ? YELLOW : OFF;
    ctx.fill();
  }
}

function cellAt(clientX, clientY) {
  const b = canvas.getBoundingClientRect();
  const x = Math.floor((clientX - b.left) / (b.width / COLS));
  const y = Math.floor((clientY - b.top) / (b.height / ROWS));
  return (x >= 0 && x < COLS && y >= 0 && y < ROWS) ? { x, y } : null;
}

let last = null;
function paintCell(x, y) { grid[y * COLS + x] = paintVal; }
function paintLine(a, b) {                       // fill gaps on fast drags
  let x0 = a.x, y0 = a.y; const x1 = b.x, y1 = b.y;
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    paintCell(x0, y0);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}
function paintAt(cx, cy) {
  const c = cellAt(cx, cy); if (!c) return;
  if (last) paintLine(last, c); else paintCell(c.x, c.y);
  last = c; draw(); dirty = true;
}

let drawing = false;
canvas.addEventListener("pointerdown", e => {
  drawing = true; last = null; canvas.setPointerCapture(e.pointerId);
  paintAt(e.clientX, e.clientY); e.preventDefault();
});
canvas.addEventListener("pointermove", e => {
  if (drawing) { paintAt(e.clientX, e.clientY); e.preventDefault(); }
});
function endDraw(e) { drawing = false; last = null; sendNow(); if (e) e.preventDefault(); }
canvas.addEventListener("pointerup", endDraw);
canvas.addEventListener("pointercancel", endDraw);

let dirty = false, lastSend = 0;
function buildFrame() {
  const f = new Uint8Array(STRIDE * ROWS);
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++)
    if (grid[y * COLS + x]) f[y * STRIDE + (x >> 3)] |= 0x80 >> (x & 7);
  return f;
}
function sendNow() {
  dirty = false; lastSend = performance.now();
  fetch("/frame", { method: "POST", body: buildFrame() }).catch(() => {});
}
setInterval(() => { if (dirty && performance.now() - lastSend > 120) sendNow(); }, 60);

const toggle = document.getElementById("toggle");
toggle.onclick = () => {
  paintVal = paintVal ? 0 : 1;
  toggle.textContent = "Drawing: " + (paintVal ? "YELLOW" : "BLACK");
  toggle.className = paintVal ? "yellow" : "black";
};
document.getElementById("clear").onclick = () => { grid.fill(0); draw(); sendNow(); };

// Conway's Game of Life on the current drawing. The edges wrap around, so gliders
// come back on the other side. The display adopts at most 4 frames a second, so
// a generation every 500 ms leaves it time to finish flipping each one.
const GEN_MS = 500;
const life = document.getElementById("life");
let lifeTimer = null;

function neighbours(x, y) {
  let n = 0;
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    if (dx || dy) n += grid[((y + dy + ROWS) % ROWS) * COLS + (x + dx + COLS) % COLS];
  }
  return n;
}

function generation() {
  const next = new Uint8Array(COLS * ROWS);
  let changed = false;
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    const i = y * COLS + x, n = neighbours(x, y);
    next[i] = (n === 3 || (n === 2 && grid[i])) ? 1 : 0;
    if (next[i] !== grid[i]) changed = true;
  }
  if (!changed) { stopLife(); return; }     // a still life or an empty display
  grid.set(next); draw(); sendNow();
}

// Classic patterns, "#" alive. Gliders and the spaceship travel, the R-pentomino
// and the acorn grow chaotically for a long time, the pulsar oscillates.
const PATTERNS = [
  [".#.", "..#", "###"],                                   // glider
  [".#..#", "#....", "#...#", "####."],                    // lightweight spaceship
  [".##", "##.", ".#."],                                   // R-pentomino
  [".#.....", "...#...", "##..###"],                       // acorn
  ["..###...###..", ".............", "#....#.#....#", "#....#.#....#",
   "#....#.#....#", "..###...###..", ".............", "..###...###..",
   "#....#.#....#", "#....#.#....#", "#....#.#....#", ".............",
   "..###...###.."],                                       // pulsar
];

// Drops 3 to 5 random patterns, randomly mirrored, at random places. The edges
// wrap, so a pattern may straddle them. Patterns too big for the display are skipped.
function seed() {
  const fits = PATTERNS.filter(p => p.length <= ROWS && p[0].length <= COLS);
  const count = 3 + Math.floor(Math.random() * 3);
  for (let k = 0; k < count; k++) {
    const p = fits[Math.floor(Math.random() * fits.length)];
    const h = p.length, w = p[0].length;
    const flipX = Math.random() < 0.5, flipY = Math.random() < 0.5;
    const ox = Math.floor(Math.random() * COLS), oy = Math.floor(Math.random() * ROWS);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (p[flipY ? h - 1 - y : y][flipX ? w - 1 - x : x] === "#") {
        grid[((oy + y) % ROWS) * COLS + (ox + x) % COLS] = 1;
      }
    }
  }
  draw(); sendNow();
}

function stopLife() {
  clearInterval(lifeTimer); lifeTimer = null;
  life.textContent = "Life"; life.className = "";
}
life.onclick = () => {
  if (lifeTimer) { stopLife(); return; }
  if (grid.every(v => !v)) seed();
  lifeTimer = setInterval(generation, GEN_MS);
  life.textContent = "Stop"; life.className = "running";
};

window.addEventListener("resize", layout);
window.addEventListener("orientationchange", layout);
layout();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404); return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/frame":
            self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        ok = len(data) == FRAME_BYTES
        if ok:
            _udp.sendto(data, (DISPLAY_IP, UDP_PORT))
        self.send_response(204 if ok else 400)
        self.end_headers()

    def log_message(self, *a):
        pass


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((DISPLAY_IP, 1)); return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    global COLS, ROWS, FRAME_BYTES, PAGE
    COLS, ROWS = display_size()
    FRAME_BYTES = stride(COLS) * ROWS
    PAGE = PAGE_TEMPLATE.replace("__COLS__", str(COLS)).replace("__ROWS__", str(ROWS))

    print(f"display is {COLS} x {ROWS} dots")
    print(f"On your phone (same WiFi) open:  http://{lan_ip()}:{HTTP_PORT}/")
    print(f"Forwarding {FRAME_BYTES}-byte frames to {DISPLAY_IP}:{UDP_PORT}")
    ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
