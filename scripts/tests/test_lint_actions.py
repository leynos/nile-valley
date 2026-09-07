"""Tests for the composite action and workflow lint gate.

The gate replaced a Make recipe that chained yamllint with actionlint in one
shell, where only the last tool decided the result. These tests pin the
replacement: the tools run in order, the first failure stops the gate, and the
failing tool is named.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import GateError
from scripts.lint_actions import main
from scripts.tests.gate_test_support import (
    activate,
    commands_run,
    empty_search_path,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

LINT_TOOLS = ("yamllint", "action-validator", "actionlint")


def _write_workflow(directory: Path, name: str) -> Path:
    """Create a placeholder workflow file; the doubles never read it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("name: example\n", encoding="utf-8")
    return path


def _write_action(directory: Path, name: str) -> Path:
    """Create a placeholder composite action manifest."""
    action_dir = directory / name
    action_dir.mkdir(parents=True, exist_ok=True)
    path = action_dir / "action.yml"
    path.write_text("name: example\n", encoding="utf-8")
    return path


def _stub_tools(mox: CmdMox, exit_codes: dict[str, int]) -> None:
    """Register every lint tool, overriding the listed exit codes."""
    for tool in LINT_TOOLS:
        mox.stub(tool).returns(exit_code=exit_codes.get(tool, 0))


def test_all_tools_run_in_order_when_everything_passes(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """Composite actions are linted before workflows, yamllint before the rest."""
    actions_dir = tmp_path / "actions"
    workflows_dir = tmp_path / "workflows"
    _write_action(actions_dir, "bootstrap")
    _write_workflow(workflows_dir, "ci.yml")

    _stub_tools(cmd_mox, {})
    activate(cmd_mox)

    main(actions_dir=actions_dir, workflows_dir=workflows_dir)

    assert commands_run(cmd_mox) == [
        "yamllint",
        "action-validator",
        "yamllint",
        "actionlint",
    ]


def test_failing_first_tool_stops_the_gate(cmd_mox: CmdMox, tmp_path: Path) -> None:
    """A yamllint failure is reported and actionlint never runs.

    This is the defect the gate script exists to fix: the shell recipe ran
    actionlint afterwards and reported its clean status to Make.
    """
    workflows_dir = tmp_path / "workflows"
    _write_workflow(workflows_dir, "ci.yml")

    _stub_tools(cmd_mox, {"yamllint": 1})
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(actions_dir=tmp_path / "absent", workflows_dir=workflows_dir)

    assert "yamllint" in str(excinfo.value)
    assert commands_run(cmd_mox) == ["yamllint"]


def test_failing_last_tool_is_reported(cmd_mox: CmdMox, tmp_path: Path) -> None:
    """An actionlint failure surfaces after a clean yamllint run."""
    workflows_dir = tmp_path / "workflows"
    _write_workflow(workflows_dir, "ci.yml")

    _stub_tools(cmd_mox, {"actionlint": 1})
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(actions_dir=tmp_path / "absent", workflows_dir=workflows_dir)

    assert "actionlint" in str(excinfo.value)
    assert commands_run(cmd_mox) == ["yamllint", "actionlint"]


def test_every_workflow_is_passed_to_both_tools(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """Both YAML suffixes are collected and handed to each tool."""
    workflows_dir = tmp_path / "workflows"
    first = _write_workflow(workflows_dir, "ci.yml")
    second = _write_workflow(workflows_dir, "release.yaml")

    _stub_tools(cmd_mox, {})
    activate(cmd_mox)

    main(actions_dir=tmp_path / "absent", workflows_dir=workflows_dir)

    expected = [str(first), str(second)]
    assert [invocation.args for invocation in cmd_mox.journal] == [expected, expected]


def test_action_validator_runs_once_per_manifest(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """Each composite action manifest is validated individually."""
    actions_dir = tmp_path / "actions"
    _write_action(actions_dir, "alpha")
    _write_action(actions_dir, "beta")

    _stub_tools(cmd_mox, {})
    activate(cmd_mox)

    main(actions_dir=actions_dir, workflows_dir=tmp_path / "absent")

    assert commands_run(cmd_mox) == [
        "yamllint",
        "action-validator",
        "action-validator",
    ]


def test_action_validator_failure_stops_before_the_next_manifest(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """The first invalid manifest ends the gate and is named in the error."""
    actions_dir = tmp_path / "actions"
    _write_action(actions_dir, "alpha")
    _write_action(actions_dir, "beta")

    _stub_tools(cmd_mox, {"action-validator": 1})
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(actions_dir=actions_dir, workflows_dir=tmp_path / "absent")

    assert "action-validator" in str(excinfo.value)
    assert "alpha" in str(excinfo.value)
    assert commands_run(cmd_mox) == ["yamllint", "action-validator"]


def test_absent_directories_are_skipped(
    cmd_mox: CmdMox, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository without actions or workflows passes without running a tool."""
    _stub_tools(cmd_mox, {})
    activate(cmd_mox)

    main(
        actions_dir=tmp_path / "absent-actions",
        workflows_dir=tmp_path / "absent-workflows",
    )

    output = capsys.readouterr().out
    assert "No composite actions found" in output
    assert "No workflows found" in output
    assert commands_run(cmd_mox) == []


def test_missing_tool_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An uninstalled linter is reported before any file is inspected.

    The search path is emptied so the check exercises real tool lookup rather
    than a stub.
    """
    with (
        empty_search_path(monkeypatch, tmp_path / "empty-bin"),
        pytest.raises(GateError) as excinfo,
    ):
        main(actions_dir=tmp_path, workflows_dir=tmp_path)

    message = str(excinfo.value)
    for tool in LINT_TOOLS:
        assert tool in message
