"""Tests for Poke-Saifu CLI interface."""

import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Poke-Saifu" in result.stdout
    assert "--output" in result.stdout
