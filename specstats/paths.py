"""Where things live. Raw and derived data go in data/private/ (gitignored)."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
SUMMARIES = ROOT / "summaries"


def private_dir():
    d = Path(os.environ.get("SPECSTATS_DATA", ROOT / "data" / "private"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_db():
    return private_dir() / "raw.sqlite"


def derived_db():
    return private_dir() / "derived.sqlite"


def settings():
    """Operator settings, e.g. {"contact": "you@example.com"} for the User-Agent."""
    p = private_dir() / "settings.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def repos():
    """The WHATWG repos to track, from config/repos.txt."""
    out = []
    for line in (CONFIG / "repos.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out
