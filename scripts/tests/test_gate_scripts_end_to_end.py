"""Behavioural tests that run the gate scripts as Make runs them.

The unit tests import each script's ``main`` and replace the tools with
cmd-mox doubles. These tests instead start the real entry point in a
subprocess against a controlled search path holding fake executables, so they
cover the parts Make actually depends on: command-line parsing, environment
resolution, the process exit code, and the diagnostic on standard error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing as typ

import pytest
from makefile_contract_support import REPO_ROOT

if typ.TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

TOOL_LOG = "GATE_TOOL_LOG"
# The fake tools run with a search path holding only themselves, so their
# interpreter has to be named absolutely.
BASH = shutil.which("bash") or "/bin/bash"


class Harness(typ.NamedTuple):
    """A controlled search path and the log the fake tools append to."""

    bin_dir: Path
    log: Path

    def add_tool(self, name: str, *, exit_code: int = 0, stdout: str = "") -> Path:
        """Install a fake executable that records its call and exits."""
        script = self.bin_dir / name
        body = f"#!{BASH}\n"
        body += f'printf "%s %s\\n" "{name}" "$*" >> "${TOOL_LOG}"\n'
        if stdout:
            body += f"printf '%b' {stdout!r}\n"
        body += f"exit {exit_code}\n"
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
        return script

    def calls(self) -> list[str]:
        """Return the names of the tools that ran, in order."""
        if not self.log.exists():
            return []
        return [
            line.split(" ", 1)[0]
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def arguments_of(self, name: str) -> list[str]:
        """Return the arguments the named tool was called with."""
        for line in self.log.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name} "):
                return line.split(" ", 1)[1].split()
        return []


@pytest.fixture(name="harness")
def harness_fixture(tmp_path: Path) -> Harness:
    """Provide an empty search path and a call log for the fake tools."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    return Harness(bin_dir=bin_dir, log=tmp_path / "tool-calls.log")


def _run(
    script: str,
    arguments: Sequence[str],
    harness: Harness,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a gate script the way Make does and return the completed process."""
    env = {
        "PATH": str(harness.bin_dir),
        TOOL_LOG: str(harness.log),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    env.update(environment or {})

    return subprocess.run(  # noqa: S603
        [sys.executable, f"scripts/{script}", *arguments],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _workflow_dir(tmp_path: Path) -> Path:
    """Create a directory holding one workflow file."""
    directory = tmp_path / "workflows"
    directory.mkdir()
    (directory / "ci.yml").write_text("name: example\n", encoding="utf-8")
    return directory


def test_lint_actions_exits_zero_when_every_tool_passes(
    harness: Harness, tmp_path: Path
) -> None:
    """A clean run exits 0 and runs both workflow tools in order."""
    for tool in ("yamllint", "action-validator", "actionlint"):
        harness.add_tool(tool)

    result = _run(
        "lint_actions.py",
        [
            "--actions-dir",
            str(tmp_path / "absent"),
            "--workflows-dir",
            str(_workflow_dir(tmp_path)),
        ],
        harness,
    )

    assert result.returncode == 0, f"expected a clean exit, got {result.stderr}"
    assert harness.calls() == ["yamllint", "actionlint"], (
        f"unexpected tool order: {harness.calls()}"
    )


def test_lint_actions_reports_the_first_failing_tool(
    harness: Harness, tmp_path: Path
) -> None:
    """A yamllint failure exits 1, names the tool, and stops the gate.

    This is the behaviour Make could not observe when the recipe chained the
    two tools in one shell.
    """
    harness.add_tool("yamllint", exit_code=1)
    harness.add_tool("action-validator")
    harness.add_tool("actionlint")

    result = _run(
        "lint_actions.py",
        [
            "--actions-dir",
            str(tmp_path / "absent"),
            "--workflows-dir",
            str(_workflow_dir(tmp_path)),
        ],
        harness,
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "yamllint (workflows) failed with exit status 1" in result.stderr, (
        f"the diagnostic must name the tool: {result.stderr!r}"
    )
    assert "actionlint" not in harness.calls(), (
        f"actionlint ran after yamllint failed: {harness.calls()}"
    )


def test_lint_actions_names_a_missing_tool(harness: Harness, tmp_path: Path) -> None:
    """An empty search path fails before any file is inspected."""
    result = _run(
        "lint_actions.py",
        ["--workflows-dir", str(_workflow_dir(tmp_path))],
        harness,
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "not installed" in result.stderr, f"unexpected diagnostic: {result.stderr!r}"
    assert harness.calls() == [], "no tool may run when one is missing"


def test_run_bun_tool_passes_arguments_after_the_separator(
    harness: Harness,
) -> None:
    """Options meant for the tool survive the script's own parsing."""
    harness.add_tool("biome")

    result = _run(
        "run_bun_tool.py",
        ["--tool", "biome", "--", "ci", "--formatter-enabled=true", "scripts"],
        harness,
    )

    assert result.returncode == 0, f"expected a clean exit, got {result.stderr}"
    assert harness.arguments_of("biome") == [
        "ci",
        "--formatter-enabled=true",
        "scripts",
    ], f"the tool's own options were not passed through: {harness.arguments_of('biome')}"


def test_tofu_gate_skips_without_its_kubeconfig(harness: Harness) -> None:
    """The opt-in variable is read from the environment, not from a flag."""
    harness.add_tool("tofu")

    result = _run("tofu_example_gate.py", ["--module", "traefik"], harness)

    assert result.returncode == 0, f"a disabled gate must pass: {result.stderr}"
    assert "Skipping traefik" in result.stdout, f"no skip reported: {result.stdout!r}"
    assert harness.calls() == [], "OpenTofu ran while the gate was disabled"


def test_tofu_gate_reports_incomplete_environment(harness: Harness) -> None:
    """Enabling the gate without its companion variables exits 1 and names them."""
    harness.add_tool("tofu")

    result = _run(
        "tofu_example_gate.py",
        ["--module", "traefik"],
        harness,
        {"TRAEFIK_KUBECONFIG_PATH": "/tmp/kubeconfig"},
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "TRAEFIK_ACME_EMAIL" in result.stderr, (
        f"the missing variable must be named: {result.stderr!r}"
    )
    assert harness.calls() == [], "OpenTofu ran with an incomplete environment"


def test_unknown_module_exits_one_without_a_traceback(harness: Harness) -> None:
    """A misspelt module reports one line rather than a stack trace."""
    harness.add_tool("tofu")

    result = _run("tofu_example_gate.py", ["--module", "traefik-typo"], harness)

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "unknown module" in result.stderr, f"unexpected output: {result.stderr!r}"
    assert "Traceback" not in result.stderr, (
        f"a gate failure must not print a traceback: {result.stderr!r}"
    )


def test_check_spelling_reports_a_finding(harness: Harness) -> None:
    """A typos finding exits 1 and names the pinned version."""
    harness.add_tool("git", stdout="README.md\\0")
    harness.add_tool("uv", exit_code=2)

    result = _run(
        "check_spelling.py", ["--typos-version", "1.48.0"], harness
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "typos@1.48.0" in result.stderr, (
        f"the pinned version must be named: {result.stderr!r}"
    )
    assert harness.calls() == ["git", "uv"], (
        f"the listing must precede the check: {harness.calls()}"
    )


def test_check_spelling_stops_when_the_listing_fails(harness: Harness) -> None:
    """A failed listing never reaches typos, unlike the shell pipeline."""
    harness.add_tool("git", exit_code=1)
    harness.add_tool("uv")

    result = _run(
        "check_spelling.py", ["--typos-version", "1.48.0"], harness
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "git ls-files" in result.stderr, f"unexpected diagnostic: {result.stderr!r}"
    assert harness.calls() == ["git"], (
        f"typos ran after the listing failed: {harness.calls()}"
    )
