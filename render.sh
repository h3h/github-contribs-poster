#!/usr/bin/env bash
# Render every theme to SVG and PNG. PNG conversion needs rsvg-convert (librsvg).
set -euo pipefail
cd "$(dirname "$0")"
for theme in tokyonight solarized; do
  python3 make_poster.py "$theme"
done
if command -v rsvg-convert >/dev/null; then
  for svg in output/*.svg; do
    rsvg-convert -w 1800 "$svg" -o "${svg%.svg}.png"
  done
else
  echo "rsvg-convert not found; skipping PNGs (try: nix shell nixpkgs#librsvg)" >&2
fi
