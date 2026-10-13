// Isometric bar-chart + coin + wordmark scene, adapted from
// assets-src/logo-3d-preview.html (read and reused per instruction -- not
// loaded as a separate file; inlined here so both the opening splash and
// the first screen's static hero can share one drawing routine). The hero
// calls render(SPLASH_DURATION) once with no animation loop (item 5); the
// splash calls play() (item 4).
const NS = "http://www.w3.org/2000/svg";
const S = 0.866;
const OX = 142;
const OY = 262;
const INK = "#0D1330";
const HB = 17;
const GAP = 52;
const HEIGHTS = [44, 78, 112, 150];

export const SPLASH_DURATION = 2.1;

function project(x, y, z) {
  return [OX + (x - y) * S, OY + (x + y) * 0.5 - z];
}

function pointsAttr(poly) {
  return poly.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
}

function svgEl(name, attrs, parent) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) {
    e.setAttribute(k, attrs[k]);
  }
  parent.appendChild(e);
  return e;
}

function clamp01(p) {
  return Math.max(0, Math.min(1, p));
}
function outCubic(p) {
  return 1 - (1 - p) ** 3;
}
function outBack(p) {
  const c = 1.70158;
  return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2;
}
function outBounce(p) {
  const n = 7.5625;
  const d = 2.75;
  if (p < 1 / d) return n * p * p;
  if (p < 2 / d) { const q = p - 1.5 / d; return n * q * q + 0.75; }
  if (p < 2.5 / d) { const q = p - 2.25 / d; return n * q * q + 0.9375; }
  const q = p - 2.625 / d;
  return n * q * q + 0.984375;
}

// root: an <svg> containing <g class="bars-scene"></g> and, optionally,
// <g class="bars-coin">, <g class="bars-word">, <text class="bars-tag">.
// Missing optional elements are simply not animated (the landing hero omits
// the wordmark/tagline since the headline is separate HTML text).
export function createBarScene(root) {
  const scene = root.querySelector(".bars-scene");
  const coin = root.querySelector(".bars-coin");
  const word = root.querySelector(".bars-word");
  const tag = root.querySelector(".bars-tag");

  const plate = svgEl("g", {}, scene);
  const T = 10;
  const px0 = -30;
  const px1 = 30;
  const py0 = -190;
  const py1 = 34;
  function plateFace(z) {
    return [project(px0, py0, z), project(px1, py0, z), project(px1, py1, z), project(px0, py1, z)];
  }
  const top = plateFace(0);
  const bot = plateFace(-T);
  svgEl("polygon", { points: pointsAttr(bot.map((p) => [p[0] + 10, p[1] + 10])), fill: INK }, plate);
  svgEl("polygon", { points: pointsAttr([top[2], top[3], bot[3], bot[2]]), fill: "#8793D6", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" }, plate);
  svgEl("polygon", { points: pointsAttr([top[1], top[2], bot[2], bot[1]]), fill: "#AEB8EA", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" }, plate);
  svgEl("polygon", { points: pointsAttr(top), fill: "#E8ECFF", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" }, plate);

  const bars = [];
  for (let i = 3; i >= 0; i -= 1) {
    const g = svgEl("g", {}, scene);
    bars[i] = {
      left: svgEl("polygon", { fill: "#00A693", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" }, g),
      right: svgEl("polygon", { fill: "#007F70", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" }, g),
      top: svgEl("polygon", { fill: "#2FD5BF", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" }, g),
      y: -GAP * i,
    };
  }

  function drawBar(i, h) {
    const b = bars[i];
    const y = b.y;
    const a = HB;
    const visible = h > 0.5;
    b.left.style.display = b.right.style.display = b.top.style.display = visible ? "" : "none";
    if (!visible) {
      return;
    }
    b.left.setAttribute("points", pointsAttr([project(-a, y + a, 0), project(a, y + a, 0), project(a, y + a, h), project(-a, y + a, h)]));
    b.right.setAttribute("points", pointsAttr([project(a, y - a, 0), project(a, y + a, 0), project(a, y + a, h), project(a, y - a, h)]));
    b.top.setAttribute("points", pointsAttr([project(-a, y - a, h), project(a, y - a, h), project(a, y + a, h), project(-a, y + a, h)]));
  }

  function render(t) {
    const pp = outCubic(clamp01(t / 0.4));
    plate.setAttribute("transform", `translate(0,${(-46 * (1 - pp)).toFixed(1)})`);
    plate.setAttribute("opacity", pp.toFixed(2));
    for (let i = 0; i < 4; i += 1) {
      const p = clamp01((t - (0.32 + 0.14 * i)) / 0.55);
      drawBar(i, HEIGHTS[i] * outBack(p));
    }
    if (coin) {
      const cp = clamp01((t - 1.0) / 0.7);
      const zRest = HEIGHTS[3] + 17;
      const z = zRest + 150 * (1 - outBounce(cp));
      const c = project(0, bars[3].y, z);
      const sx = Math.max(0.12, Math.abs(Math.cos((1 - cp) * Math.PI * 5)));
      coin.setAttribute("transform", `translate(${c[0].toFixed(1)},${c[1].toFixed(1)}) scale(${sx.toFixed(3)},1)`);
      coin.setAttribute("opacity", clamp01(cp * 8).toFixed(2));
    }
    if (word) {
      const wp = outCubic(clamp01((t - 1.35) / 0.45));
      word.setAttribute("transform", `translate(0,${(16 * (1 - wp)).toFixed(1)})`);
      word.setAttribute("opacity", wp.toFixed(2));
    }
    if (tag) {
      tag.setAttribute("opacity", clamp01((t - 1.65) / 0.35).toFixed(2));
    }
  }

  function play(onDone) {
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      render(SPLASH_DURATION);
      if (onDone) onDone();
      return;
    }
    const t0 = performance.now();
    function tick(now) {
      const t = (now - t0) / 1000;
      render(Math.min(t, SPLASH_DURATION));
      if (t < SPLASH_DURATION) {
        requestAnimationFrame(tick);
      } else if (onDone) {
        onDone();
      }
    }
    requestAnimationFrame(tick);
  }

  return { render, play };
}
