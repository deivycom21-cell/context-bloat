# Contributing to context-bloat

## Setup

```sh
git clone https://github.com/deivycom21-cell/context-bloat
cd context-bloat
uv sync --extra dev
```

## Running tests

```sh
uv run pytest -q
```

All 27 tests must pass before opening a PR.

## Running the CLI locally

```sh
uv run context-bloat scan .
uv run context-bloat fix .
uv run context-bloat --json scan .
```

## Project structure

```
src/context_bloat/
  scanner.py   — scan(), health score, anti-pattern detection
  fixer.py     — fix(), generates *.optimized.md (never overwrites originals)
  cli.py       — argparse entry point, --json / --share / --no-funnel flags
tests/
  test_scanner.py     — tokens, heavy files, anti-patterns, CLI flags
  test_no_network.py  — enforces 100% offline (patches socket.socket)
```

## Key constraints

- **100% offline** — no network calls, no model downloads. The `test_no_network.py` suite enforces this.
- **Single production dependency** — only `rich`. Do not add more.
- **Token heuristic** — `max(1, len(text) // 4)`. Do not replace with a tiktoken/model-specific counter.

## Opening a PR

1. Fork the repo and create a branch from `master`.
2. Make your changes and add or update tests.
3. Run `uv run pytest -q` — all tests must pass.
4. Open a PR with a clear description of what and why.
