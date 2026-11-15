"""Secrets and generated artifacts must never be tracked by git."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
# [ \t] not \s: an empty "API_KEY=" must not swallow the next line as its value.
KEY_ASSIGNMENT = re.compile(r"(?i)(api[_-]?key|apikey|secret|token)[ \t]*[=:][ \t]*['\"]?([A-Za-z0-9_\-]{24,})")


def _tracked() -> list[str]:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def test_no_env_or_artifacts_tracked() -> None:
    files = _tracked()
    assert not [f for f in files if Path(f).name == ".env" or Path(f).name.startswith(".env.") and
                not f.endswith(".env.example")]
    assert not [f for f in files if f.endswith((".pkl", ".parquet", ".sqlite3", ".db"))]
    assert "backend/.env.example" in files


def test_no_hardcoded_keys_in_tracked_files() -> None:
    hits = []
    for f in _tracked():
        path = REPO / f
        if path.suffix not in {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".txt", ".example", ""}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        hits += [f"{f}: {m.group(1)}" for m in KEY_ASSIGNMENT.finditer(text) if "test-secret" not in m.group(2)]
    assert not hits, hits
