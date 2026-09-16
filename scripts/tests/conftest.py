"""Pytest configuration for scripts tests.

Notes
-----
Ensures the repository root is on ``sys.path`` so script modules import
correctly during collection.

Examples
--------
>>> # Pytest invokes pytest_configure automatically during collection.
"""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path


def _cmd_mox_plugins() -> tuple[str, ...]:
    """Register the ``cmd_mox`` fixture only when the package is installed."""
    # A narrower pytest invocation may omit cmd-mox; an unconditional
    # registration would break it. A test that needs the fixture fails with
    # "fixture not found" rather than skipping.
    return ("cmd_mox.pytest_plugin",) if find_spec("cmd_mox") else ()


pytest_plugins = _cmd_mox_plugins()


def pytest_configure() -> None:
    """Configure sys.path for script test collection.

    Notes
    -----
    Adds the repository root to ``sys.path`` so tests can import scripts.
    """
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
