#!/usr/bin/env python3
"""Measure a user's commits per language per month from git history into data/languages.json.

Usage: fetch_languages.py [--local REPO_DIR ...] [--author PATTERN ...] [--branches]

Sources:
  - every repo GitHub lists commit contributions for (cloned into .cache/repos/ unless a --local
    clone of it exists), which in practice is the public slice;
  - any --local clones, e.g. private work repos GitHub only reports as counts.

By default only each repo's default branch counts, matching GitHub. --branches also counts
unmerged work on local and origin branches, skipping branches whose pull request was merged
(their work is already on the default branch, often squashed into one commit).

Each commit by the author counts as 1, split across languages by lines changed in code files
(docs, config, data, lockfiles, and vendored/generated paths are ignored). Only aggregate monthly
counts are written - no repo names, paths, or messages.
"""
import argparse, json, os, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent

LANGS = {
    "Ruby": "rb rake gemspec ru", "JavaScript": "js mjs cjs jsx", "TypeScript": "ts tsx mts cts",
    "Python": "py", "Shell": "sh bash zsh fish", "Nix": "nix", "HTML": "html htm erb haml slim liquid",
    "CSS": "css scss sass less", "CoffeeScript": "coffee", "Go": "go", "Rust": "rs", "Elixir": "ex exs",
    "Java": "java", "Kotlin": "kt kts", "Swift": "swift", "Objective-C": "m mm", "C": "c h",
    "C++": "cc cpp cxx hpp hh", "C#": "cs", "PHP": "php", "SQL": "sql", "Lua": "lua", "Clojure": "clj cljs cljc",
    "Haskell": "hs", "Elm": "elm", "Scala": "scala", "Lisp": "el lisp scm", "Vim script": "vim",
    "Perl": "pl pm", "Erlang": "erl", "Dart": "dart", "Zig": "zig", "Svelte": "svelte", "Vue": "vue",
}
BY_EXT = {ext: lang for lang, exts in LANGS.items() for ext in exts.split()}
BY_NAME = {"Gemfile": "Ruby", "Rakefile": "Ruby", "Guardfile": "Ruby", "Capfile": "Ruby", "Vagrantfile": "Ruby",
           "Brewfile": "Ruby", "Makefile": "Shell", "Dockerfile": "Shell"}
SKIP = re.compile(r"(^|/)(vendor|node_modules|dist|build|coverage|tmp|\.bundle)/|\.min\.(js|css)$|(^|/)db/schema\.rb$")


def language(path):
    if SKIP.search(path):
        return None
    name = path.rsplit("/", 1)[-1]
    if name in BY_NAME:
        return BY_NAME[name]
    return BY_EXT.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout


def slug(remote):
    m = re.search(r"github\.com[:/](.+?/.+?)(\.git)?/?$", remote.strip())
    return m.group(1).lower() if m else None


def default_ref(repo):
    ref = git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD").strip()
    return ref if ref and ref != "origin/HEAD" else "HEAD"


def gql(query):
    return json.loads(subprocess.check_output(["gh", "api", "graphql", "-f", f"query={query}"]))["data"]


def visible_repos(login, years):
    repos = set()
    for y in years:
        c = gql(f'{{user(login:"{login}"){{contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z")'
                f'{{commitContributionsByRepository(maxRepositories:100){{repository{{nameWithOwner}}}}}}}}}}')
        repos |= {r["repository"]["nameWithOwner"] for r in c["user"]["contributionsCollection"]["commitContributionsByRepository"]}
    return repos


def merged_pr_branches(repo):
    name = slug(git(repo, "remote", "get-url", "origin"))
    if not name:
        return set()
    out = subprocess.run(["gh", "pr", "list", "--repo", name, "--state", "merged", "--limit", "5000",
                          "--json", "headRefName", "--jq", ".[].headRefName"], capture_output=True, text=True).stdout
    return set(out.split())


def refs_to_scan(repo, branches):
    """The default branch, plus (with branches) every local/origin branch whose PR hasn't merged."""
    refs = [default_ref(repo)]
    if branches:
        merged = merged_pr_branches(repo)
        for ref in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin").split():
            name = ref.removeprefix("origin/")
            if name != "HEAD" and ref != "origin" and name not in merged:
                refs.append(ref)
    return refs


def measure(repo, authors, months, branches=False):
    """Add this repo's commits by the author into months[YYYY-MM][language]; return the commit count."""
    log = git(repo, "log", *refs_to_scan(repo, branches), "--no-merges", "--numstat", "--format=@%aI",
              *[f"--author={a}" for a in authors])
    commits = 0
    def flush(month, lines):
        nonlocal commits
        code = sum(lines.values())
        if month and code:
            commits += 1
            for lang, n in lines.items():
                months[month][lang] += n / code
    month, lines = None, defaultdict(int)
    for row in log.splitlines():
        if row.startswith("@"):
            flush(month, lines)
            month, lines = row[1:8], defaultdict(int)
        elif row.strip():
            added, deleted, path = row.split("\t", 2)
            lang = language(path.split(" => ")[-1].rstrip("}"))
            if lang and added != "-":
                lines[lang] += int(added) + int(deleted)
    flush(month, lines)
    return commits


def main():
    contribs = json.loads((HERE / "data" / "contributions.json").read_text())
    login = contribs["login"]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--local", nargs="*", default=[], type=Path, help="local clones to measure")
    ap.add_argument("--author", action="append", help="git --author pattern (default: git user.name and login)")
    ap.add_argument("--branches", action="store_true", help="also count unmerged branch commits")
    ap.add_argument("--cache", type=Path, default=HERE / ".cache" / "repos")
    args = ap.parse_args()
    authors = args.author or [a for a in [git(".", "config", "user.name").strip(), login] if a]
    years = sorted({int(d[:4]) for d, _ in contribs["days"]})

    local = {}
    for path in args.local:
        if (path / ".git").exists():
            local[slug(git(path, "remote", "get-url", "origin")) or str(path)] = path
        else:
            print(f"skipping {path}: not a git repo", file=sys.stderr)

    months = defaultdict(lambda: defaultdict(float))
    total = 0
    for name in sorted(visible_repos(login, years)):
        if name.lower() in local:
            continue
        dest = args.cache / name.replace("/", "__")
        if dest.exists():
            subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin"], check=False)
        else:
            subprocess.run(["gh", "repo", "clone", name, str(dest), "--", "--quiet"], check=False)
        if dest.exists():
            n = measure(dest, authors, months, args.branches)
            total += n
            print(f"{n:6} {name}", file=sys.stderr)
    for path in local.values():
        n = measure(path, authors, months, args.branches)
        total += n
        print(f"{n:6} (local) {path.name}", file=sys.stderr)

    out = HERE / "data" / "languages.json"
    out.write_text(json.dumps({"authors": authors, "commits": total, "branches": args.branches,
                               "months": {m: {l: round(v, 2) for l, v in sorted(ls.items())} for m, ls in sorted(months.items())}},
                              indent=1) + "\n")
    print(f"wrote {out} ({total} commits)")


if __name__ == "__main__":
    main()
