"""Where things live. Raw GitHub objects go in data/github/ (committed);
local-only output goes in data/private/ (gitignored)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"


def github_dir():
    """Committed raw GitHub objects: {owner}/{repo}/issues/{number}/index.json."""
    return Path(os.environ.get("SPECSTATS_GITHUB", ROOT / "data" / "github"))


def private_dir():
    d = Path(os.environ.get("SPECSTATS_DATA", ROOT / "data" / "private"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def repos():
    """The WHATWG repos to track, from config/repos.txt."""
    return parse_repos((CONFIG / "repos.txt").read_text())


def parse_repos(text):
    """The uncommented repos in a repos.txt, in order."""
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out
