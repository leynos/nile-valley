"""Tests for the Node tool runner.

The runner replaced a shell conditional in the Makefile that chose between an
installed tool and `bun x`. These tests pin both branches and confirm the
tool's exit status still decides the gate.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import GateError
from scripts.run_bun_tool import main
from scripts.tests.gate_test_support import (
    activate,
    commands_run,
    empty_search_path,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

ABSENT_TOOL = "nile-valley-absent-tool"


def test_installed_tool_runs_directly(cmd_mox: CmdMox) -> None:
    """An installed tool is preferred over an ephemeral download."""
    cmd_mox.stub("biome").returns(exit_code=0)
    cmd_mox.stub("bun").returns(exit_code=0)
    activate(cmd_mox)

    main("ci", "scripts", tool="biome", package="@biomejs/biome@2.3.1")

    assert commands_run(cmd_mox) == ["biome"]
    assert cmd_mox.journal[0].args == ["ci", "scripts"]


def test_absent_tool_falls_back_to_bun_with_the_pinned_package(
    cmd_mox: CmdMox,
) -> None:
    """The pinned package spec reaches `bun x` so the version stays fixed."""
    cmd_mox.stub("bun").returns(exit_code=0)
    activate(cmd_mox)

    main("ci", "scripts", tool=ABSENT_TOOL, package="@biomejs/biome@2.3.1")

    assert commands_run(cmd_mox) == ["bun"]
    assert cmd_mox.journal[0].args == [
        "x",
        "--package=@biomejs/biome@2.3.1",
        ABSENT_TOOL,
        "ci",
        "scripts",
    ]


def test_absent_tool_without_a_package_runs_bun_by_name(cmd_mox: CmdMox) -> None:
    """Without a package spec, `bun x` resolves the tool by name."""
    cmd_mox.stub("bun").returns(exit_code=0)
    activate(cmd_mox)

    main("--version", tool=ABSENT_TOOL)

    assert cmd_mox.journal[0].args == ["x", ABSENT_TOOL, "--version"]


def test_failing_tool_fails_the_gate(cmd_mox: CmdMox) -> None:
    """A lint finding from the installed tool is reported, not swallowed."""
    cmd_mox.stub("biome").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main("ci", "scripts", tool="biome")

    assert "biome" in str(excinfo.value)


def test_failing_bun_fallback_fails_the_gate(cmd_mox: CmdMox) -> None:
    """A failure from the fallback names the tool it was running."""
    cmd_mox.stub("bun").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main("ci", tool=ABSENT_TOOL)

    assert ABSENT_TOOL in str(excinfo.value)


def test_missing_bun_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With neither the tool nor bun available the remediation names bun."""
    with (
        empty_search_path(monkeypatch, tmp_path / "empty-bin"),
        pytest.raises(GateError) as excinfo,
    ):
        main("ci", tool=ABSENT_TOOL)

    assert "bun" in str(excinfo.value)
