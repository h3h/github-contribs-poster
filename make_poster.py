#!/usr/bin/env python3
"""Render the all-time GitHub poster (yearly skyline + lifetime heatmap) as SVG.

Usage: make_poster.py [tokyonight|solarized] [--eras eras.yaml]
Reads data/contributions.json and the eras file, writes output/.
"""
import argparse, calendar, json, sys, datetime as dt
from pathlib import Path

HERE = Path(__file__).parent
DATA = json.loads((HERE / "data" / "contributions.json").read_text())
LOGIN, AS_OF, DAYS = DATA["login"], DATA["as_of"], DATA["days"]
# Private (restricted) contributions are only available as per-year counts.
PRIV = {int(y): n for y, n in DATA["private_by_year"].items()}

THEMES = {
    "solarized": dict(bg="#002b36", band="#073642", muted="#586e75", fg="#839496", bright="#93a1a1",
                      accent="#b58900", pub="#b58900", priv="#268bd2", sub="#2aa198",
                      bins=["#073642", "#0f5257", "#1d7a73", "#2aa198", "#8f9a2c", "#b58900"]),
    # Tokyo Night (folke/tokyonight.nvim "night"), pushed toward magenta/pink.
    "tokyonight": dict(bg="#1a1b26", band="#24283b", muted="#565f89", fg="#a9b1d6", bright="#c0caf5",
                       accent="#ff007c", pub="#ff007c", priv="#9d7cd8", sub="#bb9af7",
                       bins=["#292e42", "#3b3566", "#5d4794", "#9d7cd8", "#c879d6", "#ff007c"]),
}
args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
args.add_argument("theme", nargs="?", default="tokyonight", choices=THEMES)
args.add_argument("--eras", type=Path, default=HERE / "eras.yaml", help="eras file (default: eras.yaml)")
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
    """Eras as (start, end or None, title lines, subtitle lines), validated to be ordered and non-overlapping."""
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
        eras.append((start, end, as_lines(e["title"]), as_lines(e.get("subtitle"))))
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

W, H = 1800, 1290 + 10 * (7 * 12.6 + 28) + 170
out = []
def add(s): out.append(s)
def text(x, y, s, size=16, fill=T["fg"], anchor="start", weight=400, family=FONT, extra=""):
    add(f'<text x="{x:.1f}" y="{y:.1f}" font-family=\'{family}\' font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}" {extra}>{s}</text>')

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="{T["bg"]}"/>')

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
for i, (start, end, titles, subs) in enumerate(ERAS):
    end = end or AS_OF
    ex = x0 + (frac_year(start) - years[0]) * bw
    ew = x0 + (frac_year(end) + 1 / 365 - years[0]) * bw - ex
    if i % 2 == 0:
        add(f'<rect x="{ex:.1f}" y="{band_top}" width="{ew:.1f}" height="{base - band_top}" fill="{T["band"]}" opacity="0.55"/>')
    era_total = sum(c for d, c in DAYS if start <= d <= end)
    meta = f"{era_span(start, end)} · {era_total:,}"
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
    add(f'<rect x="{bx:.1f}" y="{base - hp:.1f}" width="{w:.1f}" height="{hp:.1f}" fill="{T["priv"]}"/>')
    add(f'<rect x="{bx:.1f}" y="{base - hp - hu:.1f}" width="{w:.1f}" height="{hu:.1f}" fill="{T["pub"]}"/>')
    text(bx + w / 2, base - hp - hu - 10, f"{by_year[y]:,}", 16, T["bright"], "middle", family=MONO)
    text(bx + w / 2, base + 30, f"’{str(y)[2:]}", 18, T["fg"], "middle", family=MONO)
add(f'<line x1="{x0}" x2="{x1}" y1="{base}" y2="{base}" stroke="{T["muted"]}" stroke-width="1.5"/>')
text(X(years[-1]) + bw / 2, base + 54, f"through {AS_OF[5:7]}/{AS_OF[8:]}", 14, T["muted"], "middle")

ly = base + 100
add(f'<rect x="{x0}" y="{ly - 14}" width="16" height="16" fill="{T["pub"]}"/>')
text(x0 + 26, ly, "public repos", 18, T["fg"])
add(f'<rect x="{x0 + 180}" y="{ly - 14}" width="16" height="16" fill="{T["priv"]}"/>')
text(x0 + 206, ly, "private repos (counts only)", 18, T["fg"])
text(x1, ly, "contributions per year", 18, T["muted"], "end")

# Lifetime heatmap: two columns of years, GitHub-style week x weekday grid.
hm_top = 1290
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
        add(f'<rect x="{cx + wk * pitch:.1f}" y="{cy + dow * pitch:.1f}" width="{cell}" height="{cell}" rx="2" fill="{color(by_day.get(key, 0))}"/>')
        d += dt.timedelta(days=1)

# Heatmap legend, bottom right of second column
lx, lyy = col_x[1] + block_w - 6 * (pitch + 2) - 200, hm_top + 9 * block_h + 26
text(lx - 10, lyy + 10, "less", 15, T["muted"], "end")
for j, (_, cc) in enumerate(BINS):
    add(f'<rect x="{lx + j * (pitch + 2):.1f}" y="{lyy}" width="{cell}" height="{cell}" rx="2" fill="{cc}"/>')
text(lx + 6 * (pitch + 2) + 6, lyy + 10, "more  (0 · 1 · 3 · 6 · 11 · 21+)", 15, T["muted"])

# Footer
text(M, H - 70, f"Source: GitHub GraphQL API, fetched {AS_OF}. Private-repo activity is exposed only as daily counts.", 16, T["muted"])
text(W - M, H - 70, f"github.com/{LOGIN}", 16, T["fg"], "end", family=MONO)
add("</svg>")

svg = HERE / "output" / f"{LOGIN}-github-all-time-{THEME}.svg"
svg.parent.mkdir(exist_ok=True)
svg.write_text("\n".join(out))
print(f"wrote {svg} ({total:,} contributions)")
