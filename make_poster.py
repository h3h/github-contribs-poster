#!/usr/bin/env python3
"""Render the all-time GitHub poster (yearly skyline + lifetime heatmap) as SVG.

Usage: make_poster.py [tokyonight|solarized] [--eras eras.yaml]
Reads data/contributions.json and the eras file, writes output/.
"""
import argparse, calendar, colorsys, html, json, sys, datetime as dt
from pathlib import Path

HERE = Path(__file__).parent
DATA = json.loads((HERE / "data" / "contributions.json").read_text())
LOGIN, AS_OF, DAYS = DATA["login"], DATA["as_of"], DATA["days"]
LANG_DATA = HERE / "data" / "languages.json"
MEASURED = json.loads(LANG_DATA.read_text())["months"] if LANG_DATA.exists() else {}
# Private (restricted) contributions are only available as per-year counts.
PRIV = {int(y): n for y, n in DATA["private_by_year"].items()}

THEMES = {
    "solarized": dict(bg="#002b36", band="#073642", muted="#586e75", fg="#839496", bright="#93a1a1",
                      accent="#b58900", pub="#b58900", priv="#268bd2", sub="#2aa198",
                      bins=["#073642", "#0f5257", "#1d7a73", "#2aa198", "#8f9a2c", "#b58900"],
                      langs={"Ruby": "#dc322f", "JavaScript": "#b58900", "TypeScript": "#268bd2", "Python": "#859900",
                             "Shell": "#2aa198", "Nix": "#6c71c4", "HTML": "#cb4b16", "CSS": "#d33682",
                             "CoffeeScript": "#93a1a1", "Other": "#586e75"},
                      lang_cycle=["#eee8d5", "#657b83", "#839496"]),
    # Tokyo Night (folke/tokyonight.nvim "night"), pushed toward magenta/pink.
    "tokyonight": dict(bg="#1a1b26", band="#24283b", muted="#565f89", fg="#a9b1d6", bright="#c0caf5",
                       accent="#ff007c", pub="#ff007c", priv="#9d7cd8", sub="#bb9af7",
                       bins=["#292e42", "#3b3566", "#5d4794", "#9d7cd8", "#c879d6", "#ff007c"],
                       langs={"Ruby": "#ffffff", "JavaScript": "#00a2ff", "TypeScript": "#00e5ff", "Python": "#3d5afe",
                              "Shell": "#7c4dff", "Nix": "#7aa2f7", "HTML": "#ff9e64", "CSS": "#c13cff",
                              "CoffeeScript": "#ff007c", "Java": "#bb9af7", "Other": "#565f89"},
                       # Desaturating does nothing to white, so estimated Ruby gets an explicit muted color.
                       langs_muted={"Ruby": "#a9b1d6"},
                       lang_cycle=["#f7768e", "#ff6ec7", "#b4f9f8"]),
}
args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
args.add_argument("theme", nargs="?", default="tokyonight", choices=THEMES)
args.add_argument("--eras", type=Path, default=HERE / "eras.yaml", help="eras file (default: eras.yaml)")
args.add_argument("--lang-scale", choices=["sqrt", "log", "linear"], default="sqrt",
                  help="height scale for the language chart (default: sqrt)")
args.add_argument("--annotate", action="store_true",
                  help="tag chart elements with data-* attributes for make_page.py's hover effects")
args.add_argument("--out", type=Path, help="output path (default: output/<login>-github-all-time-<theme>.svg)")
args = args.parse_args()
THEME = args.theme
T = THEMES[THEME]


def parse_when(value, is_end):
    """YYYY, YYYY-MM, or YYYY-MM-DD (YAML may hand us an int or a date) -> ISO date string."""
    s = value.isoformat() if isinstance(value, dt.date) else str(value)
    parts = s.split("-")
    try:
        y, m, d = int(parts[0]), int(parts[1]) if len(parts) > 1 else None, int(parts[2]) if len(parts) > 2 else None
        if len(parts) > 3 or len(parts[0]) != 4:
            raise ValueError
        if m is None:
            m, d = (12, 31) if is_end else (1, 1)
        elif d is None:
            d = calendar.monthrange(y, m)[1] if is_end else 1
        return dt.date(y, m, d).isoformat()
    except (ValueError, IndexError):
        raise ValueError(f"bad date {value!r}; use YYYY, YYYY-MM, or YYYY-MM-DD") from None


def as_lines(value):
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def load_eras(path):
    """Eras as (start, end or None, title lines, subtitle lines, language shares), validated to be ordered and non-overlapping."""
    if not path.exists():
        return []
    try:
        import yaml
    except ImportError:
        sys.exit(f"make_poster.py: reading {path.name} needs PyYAML: pip install -r requirements.txt")
    doc = yaml.safe_load(path.read_text()) or {}
    eras = []
    for n, e in enumerate(doc.get("eras") or [], 1):
        where = f"{path.name}: era {n}"
        try:
            if not isinstance(e, dict) or not e.get("title") or "start" not in e:
                raise ValueError("needs at least a title and a start")
            start = parse_when(e["start"], is_end=False)
            end = parse_when(e["end"], is_end=True) if e.get("end") is not None else None
        except ValueError as err:
            sys.exit(f"{where}: {err}")
        where += f" ({as_lines(e['title'])[0]})"
        if end and end < start:
            sys.exit(f"{where}: ends before it starts")
        if eras:
            prev_end = eras[-1][1]
            if prev_end is None:
                sys.exit(f"{where}: only the last era can leave out an end date")
            if start <= prev_end:
                sys.exit(f"{where}: starts on or before the previous era ends ({prev_end}); eras must be in order and not overlap")
        langs = e.get("languages") or {}
        if not isinstance(langs, dict) or not all(isinstance(v, (int, float)) and v > 0 for v in langs.values()):
            sys.exit(f"{where}: languages must map language names to positive weights, e.g. {{Ruby: 70, JavaScript: 30}}")
        weight = sum(langs.values())
        eras.append((start, end, as_lines(e["title"]), as_lines(e.get("subtitle")), {str(k): v / weight for k, v in langs.items()}))
    return eras


ERAS = load_eras(args.eras)
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
MONO = 'ui-monospace, "SF Mono", Menlo, monospace'

by_day = {d: c for d, c in DAYS}
years = sorted({int(d[:4]) for d, _ in DAYS})
by_year = {y: 0 for y in years}
for d, c in DAYS:
    by_year[int(d[:4])] += c
total = sum(by_year.values())
priv_total = sum(PRIV.values())
peak_day = max(DAYS, key=lambda x: x[1])
active_days = sum(1 for _, c in DAYS if c)

def streak():
    best = cur = 0
    for _, c in DAYS:
        cur = cur + 1 if c else 0
        best = max(best, cur)
    return best

W = 1800
out = []
def add(s): out.append(s)
def tag(cls, **data):
    """class + data-* attributes for interactive pages; nothing for the static poster."""
    if not args.annotate:
        return ""
    return f' class="{cls}"' + "".join(f' data-{k}="{html.escape(str(v), quote=True)}"' for k, v in data.items())
def text(x, y, s, size=16, fill=T["fg"], anchor="start", weight=400, family=FONT, extra=""):
    add(f'<text x="{x:.1f}" y="{y:.1f}" font-family=\'{family}\' font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}" {extra}>{s}</text>')


# Header
M = 110
text(M, 150, LOGIN, 96, T["bright"], weight=700)
text(M + 190, 150, f"on GitHub · {years[0]} – {years[-1]}", 56, T["fg"], weight=300)
stats = [(f"{total:,}", "contributions"), (f"{active_days:,}", "active days"),
         (f"{streak()}", "day best streak"), (f"{peak_day[1]}", f"peak day · {peak_day[0]}"),
         (f"{round(100 * priv_total / total)}%", "in private repos")]
sx = M
for v, label in stats:
    text(sx, 250, v, 44, T["accent"], weight=600)
    text(sx, 282, label, 18, T["muted"])
    sx += 320

# Skyline
top, base = 500, 1060
x0, x1 = M, W - M
bw = (x1 - x0) / len(years)
ymax = max(by_year.values())
scale = (base - top - 60) / ymax
X = lambda y: x0 + (y - years[0]) * bw

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
def frac_year(iso):
    d = dt.date.fromisoformat(iso)
    return d.year + (d - dt.date(d.year, 1, 1)).days / (dt.date(d.year + 1, 1, 1) - dt.date(d.year, 1, 1)).days
def era_span(start, end):
    sy, sm, ey, em = int(start[:4]), int(start[5:7]), int(end[:4]), int(end[5:7])
    if sm == 1 and (em == 12 or end == AS_OF):
        return f"{sy}–{str(ey)[2:]}" if sy != ey else str(sy)
    if sy == ey:
        return f"{MONTHS[sm - 1]}–{MONTHS[em - 1]} ’{str(sy)[2:]}"
    start_s = str(sy) if sm == 1 else f"{MONTHS[sm - 1]} ’{str(sy)[2:]}"
    end_s = f"’{str(ey)[2:]}" if em == 12 or end == AS_OF else f"{MONTHS[em - 1]} ’{str(ey)[2:]}"
    return f"{start_s}–{end_s}"

band_top = top - 110
for i, (start, end, titles, subs, shares) in enumerate(ERAS):
    end = end or AS_OF
    ex = x0 + (frac_year(start) - years[0]) * bw
    ew = x0 + (frac_year(end) + 1 / 365 - years[0]) * bw - ex
    era_total = sum(c for d, c in DAYS if start <= d <= end)
    meta = f"{era_span(start, end)} · {era_total:,}"
    if i % 2 == 0 or args.annotate:
        mix = " · ".join(f"{l} {round(v * 100)}%" for l, v in sorted(shares.items(), key=lambda x: -x[1]))
        add(f'<rect x="{ex:.1f}" y="{band_top}" width="{ew:.1f}" height="{base - band_top}" fill="{T["band"]}" '
            f'opacity="{0.55 if i % 2 == 0 else 0}"'
            f'{tag("era", title=" · ".join(titles), sub=" · ".join(subs), span=era_span(start, end), total=era_total, mix=mix)}/>')
    if ew < 110:  # too narrow for stacked labels: run them vertically down the band
        ty = band_top + 16
        for tx, s_, size, fill, fam, w8 in [(ex + ew / 2 - 15, " · ".join(t.upper() for t in titles), 16, T["bright"], FONT, 600),
                                            (ex + ew / 2 + 9, meta, 13, T["muted"], MONO, 400)]:
            text(tx, ty, s_, size, fill, weight=w8, family=fam, extra=f'letter-spacing="1" transform="rotate(90 {tx:.1f} {ty})"')
        continue
    ty = band_top + 30
    for t in titles:
        text(ex + 14, ty, t.upper(), 18, T["bright"], weight=600, extra='letter-spacing="2"'); ty += 23
    for t in subs:
        text(ex + 14, ty, t, 16, T["sub"]); ty += 22
    text(ex + 14, ty + 2, meta, 15, T["muted"], family=MONO)

for y in years:
    pv = PRIV[y]; pu = by_year[y] - pv
    bx = X(y) + bw * 0.16; w = bw * 0.68
    hp, hu = pv * scale, pu * scale
    add(f'<g{tag("bar", year=y, total=by_year[y], pub=pu, priv=pv)}>')
    add(f'<rect x="{bx:.1f}" y="{base - hp:.1f}" width="{w:.1f}" height="{hp:.1f}" fill="{T["priv"]}"/>')
    add(f'<rect x="{bx:.1f}" y="{base - hp - hu:.1f}" width="{w:.1f}" height="{hu:.1f}" fill="{T["pub"]}"/>')
    if args.annotate:  # a hover target the full height of the column, so short bars are easy to hit
        add(f'<rect x="{X(y):.1f}" y="{top - 20}" width="{bw:.1f}" height="{base - top + 20}" fill="transparent"/>')
    text(bx + w / 2, base - hp - hu - 10, f"{by_year[y]:,}", 16, T["bright"], "middle", family=MONO)
    add("</g>")
    text(bx + w / 2, base + 30, f"’{str(y)[2:]}", 18, T["fg"], "middle", family=MONO)
add(f'<line x1="{x0}" x2="{x1}" y1="{base}" y2="{base}" stroke="{T["muted"]}" stroke-width="1.5"/>')
text(X(years[-1]) + bw / 2, base + 52, f"through {AS_OF[5:7]}/{AS_OF[8:]}", 14, T["muted"], "middle")

# Languages: inverted, smoothed, stacked area hanging below the bars, on the same x axis.
# Bright = commits measured from git history (fetch_languages.py); muted = the rest of that
# month's contributions, split by the era's declared `languages` mix in eras.yaml.
month_keys = [f"{y}-{m:02d}" for y in years for m in range(1, 13) if f"{y}-{m:02d}" <= AS_OF[:7]]
contrib_month = {k: 0 for k in month_keys}
for d, c in DAYS:
    if d <= AS_OF:
        contrib_month[d[:7]] += c
def era_shares(month):
    for start, end, _, _, shares in ERAS:
        if start[:7] <= month <= (end or AS_OF)[:7]:
            return shares
    return {}
measured, declared = {}, {}
for k in month_keys:
    meas = MEASURED.get(k, {})
    rest = max(0, contrib_month[k] - sum(meas.values()))
    measured[k] = meas
    declared[k] = {l: rest * w for l, w in era_shares(k).items()}
lang_total = {}
for k in month_keys:
    for src in (measured[k], declared[k]):
        for l, v in src.items():
            lang_total[l] = lang_total.get(l, 0) + v
# Every language with at least 5 commits' worth of activity gets its own band; the rest is "Other".
TOP = [l for l, v in sorted(lang_total.items(), key=lambda x: -x[1]) if l != "Other" and v >= 5][:12]
order = TOP + (["Other"] if set(lang_total) - set(TOP) else [])
cycle = iter(T["lang_cycle"])
lang_color = {l: T["langs"].get(l) or next(cycle, T["langs"]["Other"]) for l in order}

def raw(src, lang):
    return [src[k].get(lang, 0) if lang != "Other" else sum(v for l, v in src[k].items() if l not in TOP) for k in month_keys]

def series(src, lang):
    vals = raw(src, lang)
    sigma, r = 2.2, 7  # gaussian smoothing over months
    wts = [2.718281828 ** (-(j * j) / (2 * sigma * sigma)) for j in range(-r, r + 1)]
    out_ = []
    for i in range(len(vals)):
        acc = norm = 0
        for j, w in zip(range(-r, r + 1), wts):
            if 0 <= i + j < len(vals):
                acc += vals[i + j] * w; norm += w
        out_.append(acc / norm)
    return out_

layers = []  # (lang, is_declared, values)
for l in order:
    for is_decl, src in ((False, measured), (True, declared)):
        vals = series(src, l)
        if max(vals, default=0) > 0.05:
            layers.append((l, is_decl, vals, raw(src, l)))
la_top = base + 70
la_h = 360
stack_max = max((sum(v[i] for _, _, v, _ in layers) for i in range(len(month_keys))), default=0)
if layers and stack_max > 0:
    # A compressed height (sqrt or log) keeps early years visible next to the 2026 surge; within
    # each month the layers keep their true proportions of that month's total.
    import math
    hscale = {"sqrt": lambda t: t ** 0.5, "log": lambda t: math.log1p(t), "linear": lambda t: t}[args.lang_scale]
    totals = [sum(v[i] for _, _, v, _ in layers) for i in range(len(month_keys))]
    k_h = la_h / hscale(stack_max)
    def thickness(v, i):
        return v / totals[i] * hscale(totals[i]) * k_h if totals[i] > 0 else 0
    mx = [x0 + (int(k[:4]) - years[0] + (int(k[5:]) - 0.5) / 12) * bw for k in month_keys]

    def curve(ys, reverse=False):
        pts = list(zip(mx, ys))
        if reverse:
            pts = pts[::-1]
        d = f"L{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for i in range(len(pts) - 1):  # Catmull-Rom -> cubic Bezier
            p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
            p3 = pts[min(i + 2, len(pts) - 1)]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
        return d

    def desaturate(hex_color, keep):
        r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, l, s_ = colorsys.rgb_to_hls(r, g, b)
        return "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hls_to_rgb(h, l, s_ * keep))

    def blend(a, b, t):
        return "#" + "".join(f"{round(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t):02x}" for i in (1, 3, 5))
    # faint gridline at a round per-month value
    grid = {"sqrt": (5, 25, 100, 250, 500, 1000), "log": (1, 5, 25, 100, 500), "linear": (50, 100, 150, 200, 250)}
    for g in (v for v in grid[args.lang_scale] if v <= stack_max):
        gy = la_top + hscale(g) * k_h
        add(f'<line x1="{x0}" x2="{x1}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{T["muted"]}" stroke-width="1" stroke-dasharray="2 6" opacity="0.6"/>')
        text(x0 - 10, gy + 4, f"{g}/mo", 13, T["muted"], "end", family=MONO)
    upper = [la_top] * len(month_keys)
    label_at = {}
    for l, is_decl, vals, raw_vals in layers:
        lower = [u + thickness(v, i) for i, (u, v) in enumerate(zip(upper, vals))]
        d = "M" + curve(upper)[1:] + " " + curve(lower, reverse=True) + " Z"
        meta_ = tag("layer", lang=l, kind="estimated" if is_decl else "measured", color=lang_color[l],
                    total=round(sum(raw_vals)), vals=json.dumps([round(v, 1) for v in raw_vals], separators=(",", ":")))
        if is_decl:  # estimated: muted fill, slightly more saturated outline
            c = lang_color[l]
            muted = T.get("langs_muted", {}).get(l)
            fill, edge = (muted, blend(c, muted, 0.5)) if muted else (desaturate(c, 0.3), desaturate(c, 0.6))
            add(f'<path d="{d}" fill="{fill}" stroke="{edge}" stroke-width="1.5" stroke-linejoin="round"{meta_}/>')
        else:
            add(f'<path d="{d}" fill="{lang_color[l]}"{meta_}/>')
        for i, (u, lo) in enumerate(zip(upper, lower)):
            best = label_at.get(l)
            if x0 + 60 < mx[i] < x1 - 60 and (not best or lo - u > best[0]):
                label_at[l] = (lo - u, i, u, lo)
        upper = lower
    # label each language where its (measured) band is thickest
    for l, (thick, i, u, lo) in label_at.items():
        if thick >= 14:
            text(mx[i], (u + lo) / 2 + 5, l, 14, T["bright"], "middle", weight=700,
                 extra=f'stroke="{T["bg"]}" stroke-width="3.5" paint-order="stroke"')
    text(x0, la_top + la_h + 34, "Code activity per month by language · smoothed · " + {"sqrt": "height on a square-root scale", "log": "height on a log scale", "linear": "linear height"}[args.lang_scale], 16, T["muted"])
    la_bottom = la_top + la_h + 34
else:
    la_bottom = base + 70

# Bar legend: direct labels in the right margin, beside the last bar's two segments.
last = years[-1]
seg_priv, seg_pub = PRIV[last] * scale, (by_year[last] - PRIV[last]) * scale
priv_y = base - seg_priv / 2
pub_y = min(base - seg_priv - seg_pub / 2, priv_y - 44)
mx_ = x1 + 10
text(mx_, pub_y - 34, "contributions", 13, T["muted"])
text(mx_, pub_y - 18, "per year", 13, T["muted"])
add(f'<rect x="{mx_}" y="{pub_y - 9}" width="12" height="12" fill="{T["pub"]}"/>')
text(mx_ + 18, pub_y + 2, "public", 15, T["fg"])
add(f'<rect x="{mx_}" y="{priv_y - 9}" width="12" height="12" fill="{T["priv"]}"/>')
text(mx_ + 18, priv_y + 2, "private", 15, T["fg"])
text(mx_ + 18, priv_y + 19, "counts only", 12, T["muted"])

# Language legend
ly = la_bottom + 40
if layers:
    lx_ = x0
    for l in order:
        item_w = 24 + len(l) * 10 + 34
        if lx_ + item_w > x1:
            lx_, ly = x0, ly + 34
        add(f'<g{tag("key", lang=l)}>')
        add(f'<rect x="{lx_}" y="{ly - 14}" width="16" height="16" rx="3" fill="{lang_color[l]}"/>')
        text(lx_ + 24, ly, l, 18, T["fg"])
        if args.annotate:
            add(f'<rect x="{lx_ - 4}" y="{ly - 20}" width="{item_w - 22}" height="28" fill="transparent"/>')
        add("</g>")
        lx_ += item_w
    ly += 34
    if any(is_decl for _, is_decl, _, _ in layers):
        text(x0, ly, "bright: measured from git history · muted: estimated from eras.yaml", 16, T["muted"])
    else:
        text(x0, ly, "measured from git history", 16, T["muted"])

# Lifetime heatmap: two columns of years, GitHub-style week x weekday grid.
hm_top = ly + 130
text(M, hm_top - 40, "EVERY DAY", 22, T["bright"], weight=600, extra='letter-spacing="3"')
cell, gap = 10, 2.6
pitch = cell + gap
block_w = 54 * pitch
col_x = [M + 70, W - M - block_w]
assert col_x[0] + block_w + 60 < col_x[1], "heatmap columns overlap"
rows_per_col = 10
block_h = 7 * pitch + 28

BINS = list(zip([0, 1, 3, 6, 11, 21], T["bins"]))
def color(c):
    col = BINS[0][1]
    for lo, cc in BINS:
        if c >= lo: col = cc
    return col

for i, y in enumerate(years):
    cx = col_x[i // rows_per_col]
    cy = hm_top + (i % rows_per_col) * block_h
    text(cx - 16, cy + 3.5 * pitch + 6, str(y), 18, T["fg"], "end", family=MONO)
    jan1 = dt.date(y, 1, 1)
    start = jan1 - dt.timedelta(days=(jan1.weekday() + 1) % 7)  # Sunday on/before Jan 1
    d = jan1
    while d.year == y:
        key = d.isoformat()
        if key > AS_OF: break
        wk = (d - start).days // 7
        dow = (d.weekday() + 1) % 7
        add(f'<rect x="{cx + wk * pitch:.1f}" y="{cy + dow * pitch:.1f}" width="{cell}" height="{cell}" rx="2" '
            f'fill="{color(by_day.get(key, 0))}"{tag("day", d=key, c=by_day.get(key, 0))}/>')
        d += dt.timedelta(days=1)

# Heatmap legend, bottom right of second column
lx, lyy = col_x[1] + block_w - 6 * (pitch + 2) - 200, hm_top + 9 * block_h + 26
text(lx - 10, lyy + 10, "less", 15, T["muted"], "end")
for j, (_, cc) in enumerate(BINS):
    add(f'<rect x="{lx + j * (pitch + 2):.1f}" y="{lyy}" width="{cell}" height="{cell}" rx="2" fill="{cc}"/>')
text(lx + 6 * (pitch + 2) + 6, lyy + 10, "more  (0 · 1 · 3 · 6 · 11 · 21+)", 15, T["muted"])

# Footer
H = hm_top + 10 * block_h + 170
chart_meta = tag("poster", login=LOGIN, theme=THEME, x0=x0, bw=f"{bw:.3f}", y0=years[0], months=len(month_keys),
                 latop=la_top, lah=la_h, bg=T["bg"], fg=T["fg"], bright=T["bright"], muted=T["muted"], band=T["band"])
out.insert(0, f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"{chart_meta}>\n'
              f'<rect width="{W}" height="{H}" fill="{T["bg"]}"/>')
text(M, H - 70, f"Source: GitHub GraphQL API, fetched {AS_OF}. Private-repo activity is exposed only as daily counts.", 16, T["muted"])
text(W - M, H - 70, f"github.com/{LOGIN}", 16, T["fg"], "end", family=MONO)
add("</svg>")

svg = args.out or HERE / "output" / f"{LOGIN}-github-all-time-{THEME}.svg"
svg.parent.mkdir(exist_ok=True)
svg.write_text("\n".join(out))
print(f"wrote {svg} ({total:,} contributions)")
