"""Make the integration's pure-Python core importable without Home Assistant."""

from __future__ import annotations

import sys
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "ai_trainer"
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))
