"""Verify that scan and fix never open any network connections."""

import socket
import pytest
from pathlib import Path
from unittest.mock import patch

from context_bloat.scanner import scan
from context_bloat.fixer import fix


def _network_error(*args, **kwargs):
    raise OSError("Network access is prohibited in context-bloat (offline-only tool)")


def test_scan_no_network(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Instructions\nDo the thing.\n")
    with patch.object(socket, "socket", side_effect=_network_error):
        result = scan(tmp_path)
    assert len(result.rule_files) == 1


def test_fix_no_network(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n\n\n\nDo the thing.\n")
    with patch.object(socket, "socket", side_effect=_network_error):
        results = fix(tmp_path)
    assert len(results) == 1
