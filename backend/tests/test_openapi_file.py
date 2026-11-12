from __future__ import annotations

from scripts.export_openapi import OUT, render


def test_committed_openapi_spec_is_current() -> None:
    assert OUT.exists(), "run: python -m scripts.export_openapi"
    assert OUT.read_text(encoding="utf-8") == render(), "API changed: run python -m scripts.export_openapi"
