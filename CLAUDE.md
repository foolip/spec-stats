# spec-stats: notes for Claude sessions

spec-stats will build dashboards about WHATWG spec maintenance from public
data, in the style of cosh (https://github.com/RByers/cosh). For now it only
collects data. Start with `docs/plan.md` (goal, ground rules, decisions
log, status), then `README.md` and `docs/extraction.md`; `docs/site-design.md`
has the design for the dashboards to come.

## Hard rules

- **Fetch only what `docs/plan.md` ground rule 1 says is approved.** Anything
  else (another source, a repo outside `whatwg/`) needs the maintainer's
  explicit approval first. `extract --dry-run` shows what a run would fetch.
- **Keep requests serial and incremental**, and respect GitHub's rate
  limits (ground rule 2).
- **Never commit `data/private/`** or a token.
- `data/github/` is committed and public: only real fetched data goes there.
  Tests write to a temporary directory (`SPECSTATS_GITHUB`).
- Python is standard library only.
- Record decisions in the decisions log with a date and the reason.
- Write American English (en-US): color, not colour.

## Tests

```
python3 -m unittest discover tests
cd web && npm ci && npm run check && npm test
```

- The frontend is in `web/` (Svelte 5, Vite, TypeScript); `docs/site-design.md`
  ("Frontend") describes it. Its dependencies are pinned exactly; add one
  only with a reason in the decisions log.
