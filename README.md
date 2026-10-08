# github-contribs-poster

An all-time GitHub contributions poster: contributions per year (public vs private) with career eras shaded behind the bars, plus every day since 2008 as a heatmap.

![Tokyo Night poster](output/h3h-github-all-time-tokyonight.png)

## Usage

```sh
./fetch_data.py [login]   # needs an authenticated `gh`; writes data/contributions.json
./render.sh               # writes output/*.svg and, with rsvg-convert, output/*.png
```

- `python3 make_poster.py solarized` renders a single theme (`tokyonight` is the default).
- Career eras are the `ERAS` list near the top of `make_poster.py`. Eras with only a known year span the whole year.
- No `rsvg-convert`? Run `nix shell nixpkgs#librsvg -c ./render.sh`.

## Data caveats

- GitHub reports private-repo activity only as counts: daily totals in the calendar plus a per-year private total. Repo, language, and contribution type exist only for the public slice.
- Contributions to private org repos appear only if "Include private contributions on my profile" is enabled.
