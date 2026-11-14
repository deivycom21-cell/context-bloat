"""Core scanning logic for context-bloat."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Agent rule file patterns (relative to repo root)
AGENT_RULE_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    ".windsurfrules",
    ".github/copilot-instructions.md",
]

AGENT_RULE_GLOBS = [
    ".claude/commands/*.md",
    ".cursor/rules/*.mdc",
]

# Heavy file extensions that may bloat context accidentally
HEAVY_EXTENSIONS = {".log", ".sql", ".csv"}
HEAVY_JSON_THRESHOLD = 100 * 1024  # 100 KB
HEAVY_DIRS = {"dist", "build"}

# Health score thresholds (% of 200k context window)
CONTEXT_WINDOW = 200_000
HEALTH_THRESHOLDS = [
    (0.02, "A+", "Healthy", "green"),
    (0.05, "B", "Moderate", "yellow"),
    (0.10, "C", "Heavy", "orange1"),
    (1.00, "D", "Bloated", "red"),
]

# Anti-pattern limits
MAX_RULE_LINES = 300
MAX_CODE_BLOCK_LINES = 30


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _load_gitignore_patterns(root: Path) -> list[str]:
    patterns = []
    for ignore_file in [root / ".gitignore", root / ".claudeignore"]:
        if ignore_file.exists():
            for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns


def _is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    rel = path.relative_to(root)
    parts = rel.parts
    # Always ignore .git, .venv, node_modules
    for part in parts:
        if part in {".git", ".venv", "node_modules", "__pycache__"}:
            return True
    rel_str = rel.as_posix()
    for pattern in patterns:
        # Simple glob-ish matching
        pat = pattern.rstrip("/")
        if pat in parts:
            return True
        if rel_str == pat or rel_str.startswith(pat + "/"):
            return True
        # wildcard suffix like *.log
        if pat.startswith("*"):
            ext = pat[1:]
            if rel_str.endswith(ext):
                return True
        # directory pattern like dist/
        if pattern.endswith("/") and pat in parts:
            return True
    return False


@dataclass
class RuleFile:
    path: Path
    rel_path: str
    lines: int
    bytes_: int
    tokens: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class HeavyFile:
    path: Path
    rel_path: str
    bytes_: int
    tokens: int
    reason: str


@dataclass
class ScanResult:
    root: Path
    rule_files: list[RuleFile]
    heavy_files: list[HeavyFile]
    total_rule_tokens: int
    health_grade: str
    health_label: str
    health_color: str
    health_pct: float


def _detect_antipatterns(content: str, path: Path) -> list[str]:
    warnings = []
    lines = content.splitlines()

    if len(lines) > MAX_RULE_LINES:
        warnings.append(f"File has {len(lines)} lines (limit: {MAX_RULE_LINES})")

    # Detect long inline code blocks
    in_block = False
    block_start = 0
    block_lines = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            if not in_block:
                in_block = True
                block_start = i + 1
                block_lines = 0
            else:
                in_block = False
                if block_lines > MAX_CODE_BLOCK_LINES:
                    warnings.append(
                        f"Inline code block of {block_lines} lines at line {block_start} "
                        f"(limit: {MAX_CODE_BLOCK_LINES}) — consider referencing a file path instead"
                    )
        elif in_block:
            block_lines += 1

    # Detect repeated lines/paragraphs (3+ consecutive identical non-empty lines or repeated paragraphs)
    seen_paragraphs: dict[str, int] = {}
    paragraphs = re.split(r"\n{2,}", content.strip())
    for para in paragraphs:
        para_norm = para.strip()
        if len(para_norm) > 20:
            seen_paragraphs[para_norm] = seen_paragraphs.get(para_norm, 0) + 1
    repeated = [p[:60] + "…" for p, count in seen_paragraphs.items() if count > 1]
    if repeated:
        warnings.append(f"Repeated paragraphs detected ({len(repeated)} duplicates)")

    return warnings


def scan(root: Path) -> ScanResult:
    root = root.resolve()
    patterns = _load_gitignore_patterns(root)

    rule_files: list[RuleFile] = []

    # Collect direct rule files
    candidate_paths: list[Path] = []
    for name in AGENT_RULE_FILES:
        p = root / name
        if p.exists() and p.is_file():
            candidate_paths.append(p)

    # Collect glob patterns
    for glob_pat in AGENT_RULE_GLOBS:
        for p in root.glob(glob_pat):
            if p.is_file():
                candidate_paths.append(p)

    for p in candidate_paths:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = len(content.splitlines())
        bytes_ = len(p.read_bytes())
        tokens = estimate_tokens(content)
        warnings = _detect_antipatterns(content, p)
        rel_path = str(p.relative_to(root)).replace("\\", "/")
        rule_files.append(RuleFile(p, rel_path, lines, bytes_, tokens, warnings))

    # Scan for heavy files NOT covered by ignore
    heavy_files: list[HeavyFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        # Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not _is_ignored(dp / d, root, patterns)
        ]
        for fname in filenames:
            fp = dp / fname
            if _is_ignored(fp, root, patterns):
                continue
            suffix = fp.suffix.lower()
            reason = None
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if suffix in HEAVY_EXTENSIONS:
                reason = f"{suffix} file ({size // 1024} KB)"
            elif suffix == ".json" and size > HEAVY_JSON_THRESHOLD:
                reason = f"Large JSON ({size // 1024} KB > 100 KB)"
            else:
                # Check if inside a heavy directory
                rel_parts = fp.relative_to(root).parts
                for heavy_dir in HEAVY_DIRS:
                    if heavy_dir in rel_parts:
                        reason = f"Inside '{heavy_dir}/' directory"
                        break

            if reason:
                try:
                    content = fp.read_text(encoding="utf-8", errors="ignore")
                    tokens = estimate_tokens(content)
                except OSError:
                    tokens = max(1, size // 4)
                rel_path = str(fp.relative_to(root)).replace("\\", "/")
                heavy_files.append(HeavyFile(fp, rel_path, size, tokens, reason))

    # Compute health score
    total_rule_tokens = sum(rf.tokens for rf in rule_files)
    health_pct = total_rule_tokens / CONTEXT_WINDOW

    grade, label, color = "D", "Bloated", "red"
    for threshold, g, l, c in HEALTH_THRESHOLDS:
        if health_pct <= threshold:
            grade, label, color = g, l, c
            break

    return ScanResult(
        root=root,
        rule_files=rule_files,
        heavy_files=heavy_files,
        total_rule_tokens=total_rule_tokens,
        health_grade=grade,
        health_label=label,
        health_color=color,
        health_pct=health_pct,
    )
