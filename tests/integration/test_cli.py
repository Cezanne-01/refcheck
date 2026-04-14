import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "refcheck", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--input" in result.stdout or "input" in result.stdout.lower()


def test_cli_requires_input():
    result = subprocess.run(
        [sys.executable, "-m", "refcheck"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
