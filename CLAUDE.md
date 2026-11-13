# spec-stats: notes for Claude sessions

spec-stats builds dashboards about WHATWG spec maintenance from public data,
in the style of cosh (https://github.com/RByers/cosh). Start with
`docs/plan.md` (goal, ground rules, decisions log, status), then `README.md`
and `docs/maintenance-load.md`.

## Hard rules

- **Fetch only what `docs/plan.md` ground rule 1 says is approved.** Anything
  else (another source, a repo outside `whatwg/`) needs the maintainer's
  explicit approval first. Fetching commands are dry runs without `--go`.
- **Keep requests serial, throttled and incremental** (ground rule 2).
- **Never commit `data/private/`**, a token, or synthetic data in `summaries/`.
- Python is standard library only; the web pages have no build step.
- Record decisions in the decisions log with a date and the reason.

## Tests

```
python3 -m unittest discover tests
```
