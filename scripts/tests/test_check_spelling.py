"""Tests for the spelling gate.

The gate replaced a `git ls-files | xargs typos` pipeline in the Makefile.
Without `pipefail` that pipeline reported only the last stage's status, so a
failure to list the files read as a clean spelling run. These tests pin both
statuses and the ordering.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import GateError
from scripts.check_spelling import main
from scripts.tests.gate_test_support import (
    activate,
    commands_run,
    empty_search_path,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

TYPOS_VERSION = "1.48.0"
LISTING = "README.md\0docs/guide.md\0"


def _stub_tools(
    mox: CmdMox,
    *,
    listing: str = LISTING,
    git_exit_code: int = 0,
    uv_exit_code: int = 0,
) -> None:
    """Register the git and uv doubles the gate drives."""
    mox.stub("git").returns(stdout=listing, exit_code=git_exit_code)
    mox.stub("uv").returns(exit_code=uv_exit_code)


def test_listing_precedes_the_check(cmd_mox: CmdMox) -> None:
    """The tracked files are listed and then handed to typos."""
    _stub_tools(cmd_mox)
    activate(cmd_mox)

    main(typos_version=TYPOS_VERSION)

    assert commands_run(cmd_mox) == ["git", "uv"], (
        "the gate must list tracked files before running typos"
    )


def test_every_tracked_file_reaches_typos(cmd_mox: CmdMox) -> None:
    """Both listed paths are passed, and the pinned version is honoured."""
    _stub_tools(cmd_mox)
    activate(cmd_mox)

    main(typos_version=TYPOS_VERSION)

    arguments = list(cmd_mox.journal[1].args)
    assert arguments[:3] == ["tool", "run", f"typos@{TYPOS_VERSION}"], (
        f"typos must run at the pinned version, got {arguments[:3]}"
    )
    assert arguments[-2:] == ["README.md", "docs/guide.md"], (
        f"every tracked file must be checked, got {arguments[-2:]}"
    )
    assert "--force-exclude" in arguments, (
        "the exclusion list must apply to explicitly named paths"
    )


def test_failing_listing_stops_before_typos(cmd_mox: CmdMox) -> None:
    """A failed listing fails the gate instead of checking nothing.

    The shell pipeline reported typos' clean status on an empty file list,
    which is the defect this script removes.
    """
    _stub_tools(cmd_mox, listing="", git_exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError, match="git ls-files"):
        main(typos_version=TYPOS_VERSION)

    assert commands_run(cmd_mox) == ["git"], (
        "typos must not run when the file listing failed"
    )


def test_spelling_error_fails_the_gate(cmd_mox: CmdMox) -> None:
    """A typos finding is reported with the pinned version named."""
    _stub_tools(cmd_mox, uv_exit_code=2)
    activate(cmd_mox)

    with pytest.raises(GateError, match=f"typos@{TYPOS_VERSION}"):
        main(typos_version=TYPOS_VERSION)

    assert commands_run(cmd_mox) == ["git", "uv"], (
        "the gate must run typos before reporting a spelling failure"
    )


def test_empty_listing_is_skipped(
    cmd_mox: CmdMox, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository with no tracked Markdown passes without invoking typos."""
    _stub_tools(cmd_mox, listing="")
    activate(cmd_mox)

    main(typos_version=TYPOS_VERSION)

    assert "skipping the spelling gate" in capsys.readouterr().out, (
        "an empty listing must report a skip rather than pass silently"
    )
    assert commands_run(cmd_mox) == ["git"], (
        "typos must not run without files to check"
    )


def test_missing_tools_are_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both tools are checked before any file is listed."""
    with (
        empty_search_path(monkeypatch, tmp_path / "empty-bin"),
        pytest.raises(GateError, match="not installed") as excinfo,
    ):
        main(typos_version=TYPOS_VERSION)

    message = str(excinfo.value)
    assert "git" in message, f"git must be named as missing, got {message}"
    assert "uv" in message, f"uv must be named as missing, got {message}"
