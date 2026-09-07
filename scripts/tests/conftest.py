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

import importlib
import sys
import types
from importlib.util import find_spec
from pathlib import Path

import pytest


def _cmd_mox_plugins() -> tuple[str, ...]:
    """Register the ``cmd_mox`` fixture only when the package is installed.

    The spelling gate runs a narrower pytest invocation that deliberately
    omits ``cmd-mox``; an unconditional registration would break it. A test
    that needs the fixture fails with "fixture not found" rather than being
    skipped silently.
    """
    return ("cmd_mox.pytest_plugin",) if find_spec("cmd_mox") else ()


pytest_plugins = _cmd_mox_plugins()

SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1]


def pytest_configure() -> None:
    """Configure sys.path for script test collection.

    Notes
    -----
    Adds the repository root to ``sys.path`` so tests can import scripts.
    """
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


@pytest.fixture(name="rollout_modules")
def rollout_modules_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[types.ModuleType, types.ModuleType, types.ModuleType]:
    """Import scripts through the top-level paths used at runtime."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIRECTORY))
    names = ("typos_rollout_cache", "typos_rollout", "generate_typos_config")
    importlib.invalidate_caches()
    cache, rollout, generator = (importlib.import_module(name) for name in names)
    return cache, rollout, generator
