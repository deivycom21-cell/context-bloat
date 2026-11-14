"""CLI entry point for context-bloat."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from .scanner import scan, ScanResult, CONTEXT_WINDOW
from .fixer import fix, FixResult

FUNNEL_URL = "https://github.com/deivycom21-cell"


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-bloat",
        description="Audit and optimize token bloat in AI agent repositories.",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--share",
        action="store_true",
        help="Redact absolute paths (replace root with <project>)",
    )
    parser.add_argument(
        "--no-funnel",
        action="store_true",
        help="Hide the promotional footer",
    )

    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan a repository for context bloat")
    scan_parser.add_argument("path", nargs="?", default=".", help="Path to scan (default: .)")

    fix_parser = subparsers.add_parser("fix", help="Generate optimized versions of rule files")
    fix_parser.add_argument("path", nargs="?", default=".", help="Path to fix (default: .)")

    return parser


def _redact(text: str, root: Path, share: bool) -> str:
    if not share:
        return text
    return text.replace(str(root), "<project>").replace(str(root).replace("\\", "/"), "<project>")


def _print_scan(result: ScanResult, console: Console, share: bool, no_funnel: bool) -> None:
    root_display = "<project>" if share else str(result.root)

    # --- Header ---
    console.print(Panel(
        f"[bold]context-bloat[/bold] scan · [dim]{root_display}[/dim]",
        box=box.ROUNDED,
        style="bold blue",
    ))

    # --- Rule Files Table ---
    if result.rule_files:
        table = Table(title="Agent Rule Files", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("File", style="cyan", no_wrap=True)
        table.add_column("Lines", justify="right")
        table.add_column("Bytes", justify="right")
        table.add_column("Tokens", justify="right", style="yellow")
        table.add_column("Warnings", style="red")

        for rf in result.rule_files:
            rel = _redact(rf.rel_path, result.root, share)
            warn_str = "; ".join(rf.warnings) if rf.warnings else "[dim]—[/dim]"
            table.add_row(rel, str(rf.lines), str(rf.bytes_), str(rf.tokens), warn_str)

        console.print(table)
    else:
        console.print("[dim]No agent rule files found.[/dim]")

    # --- Context Health Score ---
    pct_display = f"{result.health_pct * 100:.1f}%"
    score_text = (
        f"[{result.health_color}][bold]{result.health_grade} · {result.health_label}[/bold][/{result.health_color}]"
        f"  —  [yellow]{result.total_rule_tokens:,}[/yellow] tokens  "
        f"([dim]{pct_display} of {CONTEXT_WINDOW:,}-token window[/dim])"
    )
    console.print(Panel(score_text, title="[bold]Context Health Score[/bold]", box=box.ROUNDED))

    # --- Heavy Files ---
    if result.heavy_files:
        h_table = Table(title="Context Traps (unignored heavy files)", box=box.SIMPLE_HEAVY)
        h_table.add_column("File", style="cyan", no_wrap=True)
        h_table.add_column("Size", justify="right")
        h_table.add_column("~Tokens", justify="right", style="yellow")
        h_table.add_column("Reason", style="red")

        for hf in result.heavy_files:
            rel = _redact(hf.rel_path, result.root, share)
            size_str = f"{hf.bytes_ // 1024} KB" if hf.bytes_ >= 1024 else f"{hf.bytes_} B"
            h_table.add_row(rel, size_str, str(hf.tokens), hf.reason)

        console.print(h_table)
    else:
        console.print("[green]No unignored heavy files detected.[/green]")

    # --- Funnel ---
    if not no_funnel and not os.environ.get("CONTEXT_BLOAT_NO_FUNNEL"):
        console.print(f"\n[dim]💡 Keep your agent context lean from day one with Crow → {FUNNEL_URL}[/dim]")


def _print_scan_json(result: ScanResult, share: bool) -> None:
    def redact(s: str) -> str:
        return _redact(s, result.root, share)

    data = {
        "root": redact(str(result.root)),
        "health": {
            "grade": result.health_grade,
            "label": result.health_label,
            "pct": round(result.health_pct * 100, 2),
            "total_tokens": result.total_rule_tokens,
            "context_window": CONTEXT_WINDOW,
        },
        "rule_files": [
            {
                "path": redact(rf.rel_path),
                "lines": rf.lines,
                "bytes": rf.bytes_,
                "tokens": rf.tokens,
                "warnings": rf.warnings,
            }
            for rf in result.rule_files
        ],
        "heavy_files": [
            {
                "path": redact(hf.rel_path),
                "bytes": hf.bytes_,
                "tokens": hf.tokens,
                "reason": hf.reason,
            }
            for hf in result.heavy_files
        ],
    }
    print(json.dumps(data, indent=2))


def _print_fix(fix_results: list[FixResult], console: Console, share: bool, root: Path) -> None:
    if not fix_results:
        console.print("[dim]No rule files found to optimize.[/dim]")
        return

    table = Table(title="Optimization Results", box=box.SIMPLE_HEAVY)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Original Tokens", justify="right")
    table.add_column("Optimized Tokens", justify="right", style="green")
    table.add_column("Savings", justify="right", style="yellow")
    table.add_column("Output")

    for fr in fix_results:
        rel = _redact(fr.rel_path, root, share)
        opt_path = _redact(str(fr.optimized_path.relative_to(root)).replace("\\", "/"), root, share)
        savings = f"{fr.savings_pct:.1f}%"
        table.add_row(rel, str(fr.original_tokens), str(fr.optimized_tokens), savings, opt_path)

    console.print(table)


def _print_fix_json(fix_results: list[FixResult], share: bool, root: Path) -> None:
    def redact(s: str) -> str:
        return _redact(s, root, share)

    data = [
        {
            "original": redact(fr.rel_path),
            "optimized": redact(str(fr.optimized_path.relative_to(root)).replace("\\", "/")),
            "original_tokens": fr.original_tokens,
            "optimized_tokens": fr.optimized_tokens,
            "savings_pct": round(fr.savings_pct, 2),
        }
        for fr in fix_results
    ]
    print(json.dumps(data, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    # Default: no subcommand → scan .
    if args.command is None:
        args.command = "scan"
        args.path = "."

    no_funnel = args.no_funnel or bool(os.environ.get("CONTEXT_BLOAT_NO_FUNNEL"))
    share = args.share
    use_json = args.json

    console = Console(highlight=False) if not use_json else None

    if args.command == "scan":
        root = Path(args.path)
        if not root.exists():
            print(f"Error: path '{args.path}' does not exist.", file=sys.stderr)
            return 1
        result = scan(root)
        if use_json:
            _print_scan_json(result, share)
        else:
            _print_scan(result, console, share, no_funnel)

    elif args.command == "fix":
        root = Path(args.path)
        if not root.exists():
            print(f"Error: path '{args.path}' does not exist.", file=sys.stderr)
            return 1
        fix_results = fix(root)
        if use_json:
            _print_fix_json(fix_results, share, root.resolve())
        else:
            _print_fix(fix_results, console, share, root.resolve())

    return 0


if __name__ == "__main__":
    sys.exit(main())
