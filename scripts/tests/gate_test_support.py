"""Shared helpers for the gate-script tests.

``plumbum`` snapshots the process environment when it is imported, so the
``PATH`` and ``CMOX_*`` variables that ``cmd-mox`` installs during replay must
be copied into ``plumbum.local`` before the code under test runs. These
helpers keep that bookkeeping in one place.
"""

from __future__ import annotations

import contextlib
import os
import typing as typ

from plumbum import local

if typ.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

    import pytest
    from cmd_mox import CmdMox


def sync_plumbum_path() -> None:
    """Align ``plumbum.local`` with the current process environment.

    Examples
    --------
    >>> sync_plumbum_path()
    """
    local.env["PATH"] = os.environ["PATH"]

    desired = {key for key in os.environ if key.startswith("CMOX_")}
    active = {key for key in local.env.keys() if key.startswith("CMOX_")}

    for key in desired:
        local.env[key] = os.environ[key]

    for key in active - desired:
        local.env.pop(key, None)


def activate(mox: CmdMox) -> None:
    """Enter the replay phase and expose the shims to ``plumbum``.

    Examples
    --------
    >>> # activate(cmd_mox)  # inside a test, after declaring doubles
    """
    mox.replay()
    sync_plumbum_path()


def commands_run(mox: CmdMox) -> list[str]:
    """Return the command names recorded during replay, in call order.

    Ordering is the property these gate scripts exist to guarantee, so tests
    assert on this list rather than on call counts alone.

    Examples
    --------
    >>> # commands_run(cmd_mox) == ["yamllint", "actionlint"]
    """
    return [invocation.command for invocation in mox.journal]


@contextlib.contextmanager
def empty_search_path(
    monkeypatch: pytest.MonkeyPatch, directory: pathlib.Path
) -> Iterator[None]:
    """Run the block with ``PATH`` pointing at an empty directory.

    This exercises the real tool lookup used by the gate scripts, so a test can
    assert on the "tool not installed" path even when the tool happens to be
    installed on the host.

    Examples
    --------
    >>> # with empty_search_path(monkeypatch, tmp_path / "empty"):
    >>> #     ...
    """
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATH", str(directory))
    sync_plumbum_path()
    try:
        yield
    finally:
        monkeypatch.undo()
        sync_plumbum_path()
