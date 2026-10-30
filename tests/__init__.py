"""Tests for the Apple Music integration."""

import json
from pathlib import Path
from typing import Any


def load_json(name: str) -> Any:
    """Load a JSON fixture with an Apple Music catalog response."""
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())
