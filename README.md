# context-bloat

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Zero Network](https://img.shields.io/badge/network-zero-green.svg)](#privacy--offline)
[![CI](https://github.com/deivycom21-cell/context-bloat/actions/workflows/ci.yml/badge.svg)](https://github.com/deivycom21-cell/context-bloat/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/context-bloat.svg)](https://pypi.org/project/context-bloat/)

Audit and optimize token bloat in AI agent repositories.

Works with **Claude Code**, **Cursor**, **Windsurf**, **OpenCode** and any tool that reads agent instruction files at startup.

---

## Why

Every agent rule file (`CLAUDE.md`, `.cursorrules`, etc.) loads into the context window **before your first prompt**. A bloated setup can burn 5-15% of a 200k-token window on boilerplate alone. `context-bloat` measures the damage and helps you fix it.

---

## Install

```sh
# one-shot, no install needed
uvx context-bloat scan .

# permanent install
pipx install context-bloat

# or with uv
uv tool install context-bloat
```

---

## Usage

```
context-bloat [--json] [--share] [--no-funnel] <command> [path]

Commands:
  scan [path]   Audit context bloat (default command, default path: .)
  fix  [path]   Generate optimized copies of rule files
```

Running `context-bloat` with no arguments is the same as `context-bloat scan .`.

---

## Supported files

| File / Pattern                      | Agent              |
|-------------------------------------|--------------------|
| `CLAUDE.md`                         | Claude Code        |
| `.claude/commands/*.md`             | Claude Code        |
| `.cursorrules`                      | Cursor             |
| `.cursor/rules/*.mdc`               | Cursor             |
| `.windsurfrules`                    | Windsurf           |
| `AGENTS.md`                         | OpenCode / generic |
| `.github/copilot-instructions.md`   | GitHub Copilot     |

---

## Example output

```
╭─────────────────────────────────────────────────────╮
│ context-bloat scan · /your/project                  │
╰─────────────────────────────────────────────────────╯

Agent Rule Files
 File                               Lines   Bytes  Tokens  Warnings
 CLAUDE.md                           342   51,360  12,437  File has 342 lines (limit: 300)
 .cursor/rules/typescript.mdc         18      412     103  —
 .github/copilot-instructions.md      45    1,203     300  —

╭──────────────────────────────────────────────────────────╮
│ Context Health Score                                     │
│ C · Heavy  —  12,840 tokens  (6.4% of 200,000-token window) │
╰──────────────────────────────────────────────────────────╯

Context Traps (unignored heavy files)
 File              Size    ~Tokens  Reason
 logs/app.log      2 MB    524,288  .log file (2048 KB)
 data/export.csv   450 KB  115,200  .csv file (450 KB)
```

---

## Health grades

| Grade | Range    | Meaning                              |
|-------|----------|--------------------------------------|
| A+    | < 2%     | Healthy — minimal cold-start cost    |
| B     | 2–5%     | Moderate — worth a review            |
| C     | 5–10%    | Heavy — optimize soon                |
| D     | > 10%    | Bloated — wastes significant budget  |

Percentage = rule file tokens ÷ 200,000 (context window).

---

## Flags

| Flag            | Effect                                                    |
|-----------------|-----------------------------------------------------------|
| `--json`        | Structured JSON output, no ANSI codes                     |
| `--share`       | Replace root path with `<project>` for screenshots        |
| `--no-funnel`   | Hide the footer link (or set `CONTEXT_BLOAT_NO_FUNNEL=1`) |

---

## `fix` command

```sh
context-bloat fix .
```

Reads every agent rule file and writes `<name>.optimized.<ext>` next to it — the original is never modified. Strips HTML/Markdown comments, collapses blank lines, removes trailing whitespace. Shows a table with token savings per file.

---

## Privacy & offline

`context-bloat` is **100% offline**. It never opens a network connection, downloads models, or phones home. Token counting uses the fast local heuristic `max(1, len(text) // 4)`. The test suite patches `socket.socket` to enforce this.

---

## Development

```sh
git clone https://github.com/deivycom21-cell/context-bloat
cd context-bloat
uv sync --extra dev
uv run pytest -q
```

---

## License

MIT © 2026 Deivy
