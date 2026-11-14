# spec-stats: notes for Claude sessions

spec-stats will build dashboards about WHATWG spec maintenance from public
data, in the style of cosh (https://github.com/RByers/cosh). For now it only
collects data. Start with `docs/plan.md` (goal, ground rules, decisions
log, status), then `README.md` and `docs/extraction.md`.

## Hard rules

- **Fetch only what `docs/plan.md` ground rule 1 says is approved.** Anything
  else (another source, a repo outside `whatwg/`) needs the maintainer's
  explicit approval first. `extract --dry-run` shows what a run would fetch.
- **Keep requests serial, throttled and incremental** (ground rule 2).
- **Never commit `data/private/`** or a token.
- `data/github/` is committed and public: only real fetched data goes there.
  Tests write to a temporary directory (`SPECSTATS_GITHUB`).
- Python is standard library only.
- Record decisions in the decisions log with a date and the reason.

## Tests

```
python3 -m unittest discover tests
```
