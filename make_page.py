#!/usr/bin/env python3
"""Turn the poster into an interactive HTML page with hover details on every chart element.

Usage: make_page.py [tokyonight|solarized] [make_poster.py options...]
Writes output/<login>-github-all-time-<theme>.html: one self-contained file, no network needed.
"""
import re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__LOGIN__ on GitHub</title>
<style>
  :root { --bg: __BG__; --fg: __FG__; --bright: __BRIGHT__; --muted: __MUTED__; --band: __BAND__; }
  html { font-size: 15pt; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 1rem/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1800px; margin: 0 auto; }
  svg.poster { display: block; width: 100%; height: auto; }
  svg.poster text { pointer-events: none; }

  .bar, .layer, .key, .era, .day { transition: opacity .18s ease, filter .18s ease; }
  .bar, .layer, .key, .day { cursor: default; }

  /* bars: lift the hovered year, fade the rest */
  .bar-focus .bar { opacity: .35; }
  .bar-focus .bar.on { opacity: 1; filter: brightness(1.2) drop-shadow(0 0 10px rgb(255 255 255 / .18)); }

  /* eras: light up the band under the pointer */
  .era:hover { opacity: .9; }

  /* languages: spotlight one language across measured + estimated bands and the legend */
  .lang-focus .layer { opacity: .16; }
  .lang-focus .layer.on { opacity: 1; filter: brightness(1.15) saturate(1.15); }
  .lang-focus .key { opacity: .35; }
  .lang-focus .key.on { opacity: 1; }
  #guide { pointer-events: none; transition: opacity .12s; }

  /* days */
  .day:hover { stroke: var(--bright); stroke-width: 2.5; filter: brightness(1.4); }

  #tip { position: fixed; z-index: 10; pointer-events: none; opacity: 0; transform: translateY(4px);
         transition: opacity .12s ease, transform .12s ease;
         min-width: 11rem; max-width: 20rem; padding: .6rem .75rem; border-radius: .6rem;
         background: color-mix(in srgb, var(--bg) 88%, white); border: 1px solid color-mix(in srgb, var(--muted) 60%, transparent);
         box-shadow: 0 10px 30px rgb(0 0 0 / .45); font-size: .8rem; }
  #tip.show { opacity: 1; transform: none; }
  #tip .h { color: var(--bright); font-weight: 650; font-size: .9rem; display: flex; align-items: center; gap: .45rem; }
  #tip .sw { width: .7rem; height: .7rem; border-radius: .2rem; flex: none; }
  #tip .s { color: var(--muted); margin-top: .1rem; }
  #tip .row { display: flex; justify-content: space-between; gap: 1rem; margin-top: .3rem; }
  #tip .row b { color: var(--bright); font-variant-numeric: tabular-nums; font-weight: 600; }
</style>
</head>
<body>
<main>
__SVG__
</main>
<div id="tip" role="status" aria-live="polite"></div>
<script>
(() => {
  const svg = document.querySelector("svg.poster");
  const D = svg.dataset;
  const x0 = +D.x0, bw = +D.bw, y0 = +D.y0, nMonths = +D.months, laTop = +D.latop, laH = +D.lah;
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const tip = document.getElementById("tip");
  const fmt = n => Math.round(n).toLocaleString();

  const guide = document.createElementNS("http://www.w3.org/2000/svg", "line");
  guide.id = "guide";
  guide.setAttribute("y1", laTop); guide.setAttribute("y2", laTop + laH);
  guide.setAttribute("stroke", D.bright); guide.setAttribute("stroke-width", "1.5");
  guide.setAttribute("stroke-dasharray", "3 4"); guide.setAttribute("opacity", "0");
  svg.appendChild(guide);

  const layers = [...svg.querySelectorAll(".layer")];
  const layerVals = new Map(layers.map(el => [el, JSON.parse(el.dataset.vals)]));
  const totals = {};
  for (const el of layers) {
    const t = totals[el.dataset.lang] ||= { measured: 0, estimated: 0, color: el.dataset.color };
    t[el.dataset.kind] += +el.dataset.total;
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function header(title, color) {
    const h = el("div", "h");
    if (color) { const sw = el("span", "sw"); sw.style.background = color; h.append(sw); }
    h.append(title);
    return h;
  }
  function row(label, value) {
    const r = el("div", "row");
    r.append(el("span", null, label), el("b", null, value));
    return r;
  }
  function show(nodes, e) {
    tip.replaceChildren(...nodes);
    tip.classList.add("show");
    const pad = 16, w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > innerHeight - 8) y = e.clientY - h - pad;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  function svgX(e) {
    const p = svg.createSVGPoint();
    p.x = e.clientX; p.y = e.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse()).x;
  }
  function focus(cls, match) {
    svg.classList.toggle(cls, !!match);
    const sel = cls === "bar-focus" ? ".bar" : ".layer, .key";
    for (const n of svg.querySelectorAll(sel)) n.classList.toggle("on", !!match && match(n));
  }
  function clear() {
    tip.classList.remove("show");
    focus("bar-focus", null);
    focus("lang-focus", null);
    guide.setAttribute("opacity", "0");
  }

  function onMove(e) {
    const t = e.target.closest(".bar, .layer, .key, .era, .day");
    if (!t) return clear();
    if (!t.classList.contains("layer")) guide.setAttribute("opacity", "0");
    if (!t.classList.contains("bar")) focus("bar-focus", null);
    if (!t.classList.contains("layer") && !t.classList.contains("key")) focus("lang-focus", null);
    const d = t.dataset;

    if (t.classList.contains("bar")) {
      focus("bar-focus", n => n === t);
      show([header(d.year), row("contributions", fmt(d.total)),
            row("public repos", fmt(d.pub)), row("private repos", fmt(d.priv))], e);
    } else if (t.classList.contains("layer")) {
      focus("lang-focus", n => n.dataset.lang === d.lang);
      const i = Math.min(nMonths - 1, Math.max(0, Math.floor((svgX(e) - x0) / bw * 12)));
      const gx = x0 + (i + 0.5) / 12 * bw;
      guide.setAttribute("x1", gx); guide.setAttribute("x2", gx); guide.setAttribute("opacity", ".7");
      const v = layerVals.get(t)[i];
      const month = MONTHS[i % 12] + " " + (y0 + Math.floor(i / 12));
      const est = d.kind === "estimated";
      show([header(d.lang, d.color),
            el("div", "s", est ? "estimated from eras.yaml" : "measured from git history"),
            row(month, (est ? "≈ " : "") + fmt(v) + (est ? " contributions" : " commits")),
            row("all-time " + d.kind, fmt(d.total))], e);
    } else if (t.classList.contains("key")) {
      focus("lang-focus", n => n.dataset.lang === d.lang);
      const tot = totals[d.lang] || { measured: 0, estimated: 0 };
      const nodes = [header(d.lang, tot.color), row("measured commits", fmt(tot.measured))];
      if (tot.estimated) nodes.push(row("estimated contributions", fmt(tot.estimated)));
      show(nodes, e);
    } else if (t.classList.contains("era")) {
      const nodes = [header(d.title)];
      if (d.sub) nodes.push(el("div", "s", d.sub));
      nodes.push(row(d.span, fmt(d.total) + " contributions"));
      if (d.mix) nodes.push(el("div", "s", "declared mix: " + d.mix));
      show(nodes, e);
    } else if (t.classList.contains("day")) {
      const date = new Date(d.d + "T00:00:00");
      const label = date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
      const c = +d.c;
      show([header(label), row(c === 1 ? "contribution" : "contributions", fmt(c))], e);
    }
  }
  svg.addEventListener("pointermove", onMove);
  svg.addEventListener("pointerdown", onMove);
  svg.addEventListener("pointerleave", clear);
  addEventListener("scroll", clear, { passive: true });
})();
</script>
</body>
</html>
"""


def main():
    theme = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "tokyonight"
    extra = [a for a in sys.argv[1:] if a != theme]
    with tempfile.TemporaryDirectory() as tmp:
        svg_path = Path(tmp) / "poster.svg"
        subprocess.run([sys.executable, str(HERE / "make_poster.py"), theme, "--annotate", "--out", str(svg_path), *extra],
                       check=True, stdout=subprocess.DEVNULL)
        svg = svg_path.read_text()
    meta = dict(re.findall(r'data-(\w+)="([^"]*)"', svg[:svg.index(">")]))
    # The poster's fixed width/height would stop it scaling; the viewBox keeps its proportions.
    svg = re.sub(r'^<svg([^>]*?) width="\d+" height="[\d.]+"', r'<svg\1 role="img" aria-label="GitHub contributions poster"', svg, count=1)
    page = PAGE
    for key, value in {"__LOGIN__": meta["login"], "__BG__": meta["bg"], "__FG__": meta["fg"], "__BRIGHT__": meta["bright"],
                       "__MUTED__": meta["muted"], "__BAND__": meta["band"], "__SVG__": svg}.items():
        page = page.replace(key, value)
    out = HERE / "output" / f"{meta['login']}-github-all-time-{theme}.html"
    out.write_text(page)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
