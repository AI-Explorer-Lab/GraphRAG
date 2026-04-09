from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def fixture_payload() -> dict:
    with open(ROOT / "tests" / "fixtures" / "video_platform_lineage.json", "r", encoding="utf-8") as f:
        return json.load(f)

