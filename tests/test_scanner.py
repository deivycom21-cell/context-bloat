"""Tests for scanner, fixer, and CLI behaviour."""

import json
import pytest
from pathlib import Path

from context_bloat.scanner import scan, estimate_tokens
from context_bloat.fixer import fix
from context_bloat.cli import main


# ── Token estimation ──────────────────────────────────────────────────────────

def test_estimate_tokens_basic():
    assert estimate_tokens("hello") == 1   # 5 // 4 = 1
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 1        # max(1, ...)


# ── Rule file detection ───────────────────────────────────────────────────────

def test_scan_finds_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# AI rules\n" * 10)
    result = scan(tmp_path)
    names = [rf.rel_path for rf in result.rule_files]
    assert "CLAUDE.md" in names


def test_scan_finds_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agent instructions\n")
    result = scan(tmp_path)
    assert any("AGENTS.md" in rf.rel_path for rf in result.rule_files)


def test_scan_finds_cursorrules(tmp_path):
    (tmp_path / ".cursorrules").write_text("rule: always indent\n")
    result = scan(tmp_path)
    assert any(".cursorrules" in rf.rel_path for rf in result.rule_files)


def test_scan_no_rule_files(tmp_path):
    result = scan(tmp_path)
    assert result.rule_files == []
    assert result.total_rule_tokens == 0


# ── Heavy file detection ──────────────────────────────────────────────────────

def test_scan_detects_log_file(tmp_path):
    (tmp_path / "app.log").write_text("log line\n" * 100)
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert "app.log" in heavy_paths


def test_scan_detects_csv_file(tmp_path):
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n")
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert "data.csv" in heavy_paths


def test_scan_detects_large_json(tmp_path):
    big_json = tmp_path / "big.json"
    big_json.write_text('{"x": "' + "y" * (110 * 1024) + '"}')
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert "big.json" in heavy_paths


def test_scan_ignores_small_json(tmp_path):
    small_json = tmp_path / "small.json"
    small_json.write_text('{"x": 1}')
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert "small.json" not in heavy_paths


def test_scan_ignores_gitignored_log(tmp_path):
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "app.log").write_text("log line\n")
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert "app.log" not in heavy_paths


def test_scan_ignores_claudeignored_csv(tmp_path):
    (tmp_path / ".claudeignore").write_text("data.csv\n")
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert "data.csv" not in heavy_paths


def test_scan_detects_dist_directory(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "bundle.js").write_text("/* minified */ " + "x=1;" * 100)
    result = scan(tmp_path)
    heavy_paths = [hf.rel_path for hf in result.heavy_files]
    assert any("dist/" in p for p in heavy_paths)


# ── Anti-pattern detection ────────────────────────────────────────────────────

def test_antipattern_long_file(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("line\n" * 350)
    result = scan(tmp_path)
    rf = result.rule_files[0]
    assert any("350 lines" in w for w in rf.warnings)


def test_antipattern_long_code_block(tmp_path):
    block = "```python\n" + "x = 1\n" * 35 + "```\n"
    (tmp_path / "CLAUDE.md").write_text(block)
    result = scan(tmp_path)
    rf = result.rule_files[0]
    assert any("code block" in w for w in rf.warnings)


def test_antipattern_repeated_paragraphs(tmp_path):
    para = "Always use type hints in Python code.\n"
    (tmp_path / "CLAUDE.md").write_text((para + "\n") * 3)
    result = scan(tmp_path)
    rf = result.rule_files[0]
    assert any("Repeated" in w for w in rf.warnings)


def test_no_antipattern_short_file(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Short\nDo things.\n")
    result = scan(tmp_path)
    rf = result.rule_files[0]
    assert rf.warnings == []


# ── Health score ──────────────────────────────────────────────────────────────

def test_health_score_healthy(tmp_path):
    # Very small file → A+ Healthy
    (tmp_path / "CLAUDE.md").write_text("# Short\nDo things.\n")
    result = scan(tmp_path)
    assert result.health_grade == "A+"
    assert result.health_label == "Healthy"


def test_health_score_bloated(tmp_path):
    # 200k+ tokens → D Bloated
    (tmp_path / "CLAUDE.md").write_text("x " * (200_000 * 4 + 100))
    result = scan(tmp_path)
    assert result.health_grade == "D"


# ── Fix / optimized output ────────────────────────────────────────────────────

def test_fix_generates_optimized_file(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\n<!-- comment -->\n\n\nDo things.\n")
    results = fix(tmp_path)
    assert len(results) == 1
    opt_path = results[0].optimized_path
    assert opt_path.exists()
    assert opt_path.name == "CLAUDE.optimized.md"
    content = opt_path.read_text()
    assert "<!-- comment -->" not in content


def test_fix_does_not_overwrite_original(tmp_path):
    original_content = "# Title\n<!-- comment -->\n"
    (tmp_path / "CLAUDE.md").write_text(original_content)
    fix(tmp_path)
    assert (tmp_path / "CLAUDE.md").read_text() == original_content


def test_fix_savings_pct(tmp_path):
    # HTML comments are stripped, so savings should be > 0
    (tmp_path / "CLAUDE.md").write_text("# Hi\n<!-- big comment here -->\n\n\n\nDo things.\n")
    results = fix(tmp_path)
    assert results[0].savings_pct >= 0


# ── CLI --share flag ──────────────────────────────────────────────────────────

def test_share_flag_hides_root(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text("# Short\nDo things.\n")
    main(["--json", "--share", "scan", str(tmp_path)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert str(tmp_path) not in data["root"]
    assert "<project>" in data["root"]


def test_share_flag_hides_paths_in_rule_files(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text("# Short\nDo things.\n")
    main(["--json", "--share", "scan", str(tmp_path)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    for rf in data["rule_files"]:
        assert str(tmp_path) not in rf["path"]


# ── CLI --json flag ───────────────────────────────────────────────────────────

def test_json_output_structure(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text("# Short\nDo things.\n")
    main(["--json", "scan", str(tmp_path)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "health" in data
    assert "rule_files" in data
    assert "heavy_files" in data


# ── Default command (no subcommand) ──────────────────────────────────────────

def test_default_scan_no_subcommand(tmp_path, monkeypatch, capsys):
    (tmp_path / "CLAUDE.md").write_text("# Short\nDo things.\n")
    monkeypatch.chdir(tmp_path)
    # Without subcommand, should default to scan .
    ret = main(["--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "rule_files" in data
