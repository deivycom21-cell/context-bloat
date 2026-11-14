"""Fix / optimize agent instruction files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .scanner import estimate_tokens, scan


@dataclass
class FixResult:
    original_path: Path
    optimized_path: Path
    rel_path: str
    original_tokens: int
    optimized_tokens: int
    savings_pct: float


def _optimize_content(text: str) -> str:
    # Remove HTML comments <!-- ... -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Remove Markdown comments (lines starting with [//]: #)
    text = re.sub(r"^\[//\]:.*$", "", text, flags=re.MULTILINE)
    # Collapse 3+ consecutive blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove trailing whitespace on each line
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)
    # Remove leading/trailing whitespace from the whole doc
    text = text.strip() + "\n"
    return text


def fix(root: Path) -> list[FixResult]:
    result = scan(root)
    fix_results: list[FixResult] = []

    for rf in result.rule_files:
        original_content = rf.path.read_text(encoding="utf-8", errors="ignore")
        optimized_content = _optimize_content(original_content)

        optimized_path = rf.path.parent / (rf.path.stem + ".optimized" + rf.path.suffix)
        optimized_path.write_text(optimized_content, encoding="utf-8")

        orig_tokens = estimate_tokens(original_content)
        opt_tokens = estimate_tokens(optimized_content)
        savings_pct = (orig_tokens - opt_tokens) / orig_tokens * 100 if orig_tokens > 0 else 0.0

        fix_results.append(
            FixResult(
                original_path=rf.path,
                optimized_path=optimized_path,
                rel_path=rf.rel_path,
                original_tokens=orig_tokens,
                optimized_tokens=opt_tokens,
                savings_pct=savings_pct,
            )
        )

    return fix_results
