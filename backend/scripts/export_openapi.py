"""Write the OpenAPI spec to docs/openapi.json (used for the API docs and Flutter client generation).

Run (from backend/):  python -m scripts.export_openapi
tests/test_openapi_file.py fails when the committed spec is out of date.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.main import create_app

OUT = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def spec() -> dict[str, Any]:
    return create_app(Settings(_env_file=None, app_env="test")).openapi()  # type: ignore[call-arg]


def render() -> str:
    return json.dumps(spec(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print("Wrote", OUT)
