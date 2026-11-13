"""Attribute GitHub accounts to organizations.

In order:
1. config/affiliations.json: explicit, optionally dated, per-login entries.
   Each must cite a public source (docs/plan.md, ground rule 3).
2. The `company` field of the account's public GitHub profile, normalized
   through the aliases in config/companies.json.
3. Otherwise "Unknown".

Bots are recognized by account type ("Bot"), a "[bot]" suffix, or
config/bots.txt.
"""

import json
import re

from . import paths

UNKNOWN = "Unknown"


def load_affiliations():
    p = paths.CONFIG / "affiliations.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    return {k.lower(): v for k, v in data.items() if not k.startswith("_")}


def load_aliases():
    p = paths.CONFIG / "companies.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    aliases = {}
    for org, names in data.items():
        if org.startswith("_"):
            continue
        aliases[_norm(org)] = org
        for n in names:
            aliases[_norm(n)] = org
    return aliases


def load_bots():
    p = paths.CONFIG / "bots.txt"
    if not p.exists():
        return set()
    return {l.strip().lower() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")}


SUFFIXES = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|gmbh|ab|as|sa|plc)\b\.?", re.I)


def _norm(s):
    s = s.strip().lower()
    s = s.lstrip("@")
    s = SUFFIXES.sub("", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def company_to_org(company, aliases):
    """Map a free-text GitHub `company` field to an organization."""
    if not company:
        return None
    norm = _norm(company)
    if not norm:
        return None
    if norm in aliases:
        return aliases[norm]
    # "@google @chromium" or "Google, Chrome team": try each part.
    for part in re.split(r"[,/|&;]|\s@|\s+and\s+", company):
        p = _norm(part)
        if p in aliases:
            return aliases[p]
    # First word ("Mozilla Corporation" -> "mozilla").
    first = norm.split()[0]
    if first in aliases:
        return aliases[first]
    return None


class Attributor:
    def __init__(self, profiles, affiliations=None, aliases=None, bots=None):
        self.profiles = {k.lower(): v for k, v in profiles.items()}
        self.affiliations = load_affiliations() if affiliations is None else affiliations
        self.aliases = load_aliases() if aliases is None else aliases
        self.bots = load_bots() if bots is None else bots

    def is_bot(self, login, typename=None):
        if typename == "Bot":
            return True
        if not login:
            return False
        l = login.lower()
        return l.endswith("[bot]") or l in self.bots

    def org(self, login, when=None):
        """Organization of `login` at ISO time `when` (dated entries need it)."""
        if not login:
            return UNKNOWN
        l = login.lower()
        for entry in self.affiliations.get(l, []):
            start, end = entry.get("from"), entry.get("until")
            if when is None or ((not start or when >= start) and (not end or when < end)):
                return entry["org"]
        profile = self.profiles.get(l) or {}
        return company_to_org(profile.get("company"), self.aliases) or UNKNOWN
