"""Tests for the shared gate-script execution helpers.

The helpers exist so that a gate stops at the first failing tool and names it.
These tests pin that behaviour: the exit status is surfaced, the offending
tool appears in the message, and OpenTofu's "changes pending" status can be
accepted without masking real failures.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import (
    GateError,
    ToolRun,
    capture_tool,
    require_env,
    require_tools,
    run_gate,
    run_tool,
    tool_path,
)
from scripts.tests.gate_test_support import activate, commands_run

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

# The gate scripts are exercised through an explicit record, replay and verify
# cycle so each test states exactly which tools ran and in which order.
pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)


def test_tool_path_reports_missing_tool() -> None:
    """An absent binary resolves to ``None`` rather than raising."""
    assert tool_path("nile-valley-no-such-tool") is None, (
        "an absent tool must resolve to None so the caller can report it"
    )


def test_require_tools_names_every_missing_tool() -> None:
    """All missing tools are listed so one run reports the full remediation."""
    with pytest.raises(GateError, match="not installed") as excinfo:
        require_tools(["nile-valley-absent-one", "nile-valley-absent-two"])

    message = str(excinfo.value)
    assert "nile-valley-absent-one" in message, f"first tool unnamed: {message}"
    assert "nile-valley-absent-two" in message, f"second tool unnamed: {message}"


def test_require_tools_accepts_present_tools(cmd_mox: CmdMox) -> None:
    """A declared double satisfies the availability check."""
    cmd_mox.stub("yamllint").returns(exit_code=0)
    activate(cmd_mox)

    require_tools(["yamllint"])


def test_require_env_names_unset_variables() -> None:
    """Empty and absent values are both reported as missing."""
    with pytest.raises(GateError, match="EXAMPLE_TOKEN") as excinfo:
        require_env(
            {"EXAMPLE_TOKEN": None, "EXAMPLE_REGION": "", "EXAMPLE_NAME": "set"},
            because="when EXAMPLE_KUBECONFIG_PATH is set",
        )

    message = str(excinfo.value)
    assert "EXAMPLE_REGION" in message, f"an empty value must count as unset: {message}"
    assert "EXAMPLE_NAME" not in message, f"a set value must not be listed: {message}"
    assert "when EXAMPLE_KUBECONFIG_PATH is set" in message, (
        f"the reason the variables are required must be stated: {message}"
    )


def test_run_tool_returns_status_for_successful_command(cmd_mox: CmdMox) -> None:
    """A zero exit status is returned and the command is recorded."""
    cmd_mox.mock("yamllint").with_args("--version").returns(exit_code=0)
    activate(cmd_mox)

    assert run_tool("yamllint", ["--version"]) == 0, (
        "a successful tool must report exit status 0"
    )
    cmd_mox.verify()
    assert commands_run(cmd_mox) == ["yamllint"], "only yamllint should have run"


def test_run_tool_raises_named_error_on_failure(cmd_mox: CmdMox) -> None:
    """A non-zero exit status names the tool and the status."""
    cmd_mox.mock("yamllint").with_args("--version").returns(exit_code=3)
    activate(cmd_mox)

    with pytest.raises(GateError, match=r"yamllint failed with exit status 3"):
        run_tool("yamllint", ["--version"])


def test_run_tool_accepts_declared_exit_codes(cmd_mox: CmdMox) -> None:
    """``tofu plan -detailed-exitcode`` returns 2 for pending changes."""
    cmd_mox.mock("tofu").with_args("plan").returns(exit_code=2)
    activate(cmd_mox)

    assert run_tool("tofu", ["plan"], ToolRun(allowed_exit_codes=(0, 2))) == 2, (
        "pending changes must be reported, not treated as a failure"
    )


def test_run_tool_still_fails_outside_declared_exit_codes(cmd_mox: CmdMox) -> None:
    """Accepting exit code 2 does not accept a genuine failure."""
    cmd_mox.mock("tofu").with_args("plan").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError, match=r"tofu failed with exit status 1"):
        run_tool("tofu", ["plan"], ToolRun(allowed_exit_codes=(0, 2)))


def test_run_tool_labels_the_step(cmd_mox: CmdMox) -> None:
    """A label distinguishes two steps that use the same binary."""
    cmd_mox.mock("tofu").with_args("validate").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError, match=r"tofu validate failed with exit status 1"):
        run_tool("tofu", ["validate"], ToolRun(label="tofu validate"))


def test_capture_tool_returns_stdout(cmd_mox: CmdMox) -> None:
    """Captured output is handed to the next step rather than to the log."""
    cmd_mox.mock("helm").with_args("template", "example").returns(
        stdout="kind: Deployment\n", exit_code=0
    )
    activate(cmd_mox)

    assert capture_tool("helm", ["template", "example"]) == "kind: Deployment\n", (
        "the rendered document must be returned verbatim"
    )
    cmd_mox.verify()


def test_capture_tool_raises_before_output_is_used(cmd_mox: CmdMox) -> None:
    """A failing producer stops the gate instead of yielding empty output."""
    cmd_mox.mock("helm").with_args("template", "example").returns(
        stdout="", exit_code=1
    )
    activate(cmd_mox)

    with pytest.raises(GateError, match=r"helm failed with exit status 1"):
        capture_tool("helm", ["template", "example"])


def test_run_gate_exits_zero_on_success(capsys: pytest.CaptureFixture[str]) -> None:
    """A gate that completes exits with status 0."""
    with pytest.raises(SystemExit) as excinfo:
        run_gate(lambda: None)

    assert excinfo.value.code == 0, (
        f"a clean gate must exit 0, got {excinfo.value.code}"
    )
    assert capsys.readouterr().err == "", "a clean gate must print nothing to stderr"


def test_run_gate_reports_gate_error_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A gate failure exits 1 with a one-line diagnostic on stderr."""

    def failing() -> None:
        message = "actionlint failed with exit status 1"
        raise GateError(message)

    with pytest.raises(SystemExit) as excinfo:
        run_gate(failing)

    assert excinfo.value.code == 1, (
        f"a failed gate must exit 1, got {excinfo.value.code}"
    )
    assert "actionlint failed with exit status 1" in capsys.readouterr().err, (
        "the diagnostic must name the failing tool on stderr"
    )


def test_run_gate_propagates_unexpected_errors() -> None:
    """Programming errors are not swallowed by the gate wrapper."""

    def broken() -> None:
        raise ValueError("bug")

    with pytest.raises(ValueError, match="bug"):
        run_gate(broken)
