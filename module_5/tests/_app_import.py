"""Helpers for importing application modules during tests and linting."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def import_app_module(name: str) -> ModuleType:
    """Import and return a module from the application package."""

    return importlib.import_module(name)
