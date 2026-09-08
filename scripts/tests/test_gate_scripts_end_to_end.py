"""Behavioural tests that run the gate scripts as Make runs them.

The unit tests import each script's ``main`` and replace the tools with
cmd-mox doubles. These tests instead start the real entry point in a
subprocess against a controlled search path holding fake executables, so they
cover the parts Make actually depends on: command-line parsing, environment
resolution, the process exit code, and the diagnostic on standard error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import typing as typ

import pytest
from makefile_contract_support import REPO_ROOT

if typ.TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from pathlib import Path

TOOL_LOG = "GATE_TOOL_LOG"

# The fake tools run with a search path holding only themselves, so their
# interpreter is named absolutely. Python rather than a shell, because a fake
# has to dispatch on its subcommand and record the bytes it was given.
FAKE_TOOL_TEMPLATE = """#!{interpreter}
import json
import pathlib
import sys

plan = json.loads(r'''{plan}''')
arguments = sys.argv[1:]
with pathlib.Path(plan["log"]).open("a", encoding="utf-8") as log:
    log.write(plan["name"] + " " + " ".join(arguments) + "\\n")

if plan["stdin_path"] and not sys.stdin.isatty():
    pathlib.Path(plan["stdin_path"]).write_bytes(sys.stdin.buffer.read())

subcommand = next((word for word in arguments if not word.startswith("-")), "")
behaviour = plan["behaviours"].get(subcommand) or plan["behaviours"][""]
if behaviour["stdout_path"]:
    sys.stdout.buffer.write(pathlib.Path(behaviour["stdout_path"]).read_bytes())
    sys.stdout.buffer.flush()
sys.exit(behaviour["exit_code"])
"""


class Behaviour(typ.NamedTuple):
    """What a fake tool should do for one invocation."""

    exit_code: int = 0
    stdout: str = ""


class Harness(typ.NamedTuple):
    """A controlled search path and the log the fake tools append to."""

    bin_dir: Path
    log: Path

    def add_tool(
        self,
        name: str,
        *,
        exit_code: int = 0,
        stdout: str = "",
        by_subcommand: Mapping[str, Behaviour] | None = None,
    ) -> Path:
        """Install a fake executable that records its call and exits.

        ``by_subcommand`` selects behaviour from the first argument that is
        not an option, which is how OpenTofu names its subcommand. That lets
        one fake accept a plan's exit status of 2 while its export succeeds.

        Output is written as bytes read back from a file rather than passed
        through the shell, so a payload containing a NUL or a backslash
        reaches the caller as the bytes the test wrote. Every fake records the
        input it was given, which is how a test proves a consumer received
        what its producer rendered.
        """
        behaviours = {
            "": Behaviour(exit_code=exit_code, stdout=stdout),
            **{key: value for key, value in (by_subcommand or {}).items()},
        }
        plan = {
            "log": str(self.log),
            "name": name,
            "stdin_path": str(self._stdin_path(name)),
            "behaviours": {
                key: {"exit_code": value.exit_code, "stdout_path": None}
                for key, value in behaviours.items()
            },
        }
        for key, value in behaviours.items():
            if not value.stdout:
                continue
            payload = self.bin_dir / f"{name}.{key or 'default'}.stdout"
            payload.write_bytes(value.stdout.encode("utf-8"))
            plan["behaviours"][key]["stdout_path"] = str(payload)

        script = self.bin_dir / name
        script.write_text(
            FAKE_TOOL_TEMPLATE.format(
                interpreter=sys.executable, plan=json.dumps(plan)
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def _stdin_path(self, name: str) -> Path:
        """Return where a fake tool records the input it was given."""
        return self.bin_dir / f"{name}.stdin"

    def stdin_of(self, name: str) -> bytes:
        """Return the bytes the named tool received on standard input."""
        path = self._stdin_path(name)
        return path.read_bytes() if path.exists() else b""

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
        """Return the arguments of the named tool's first call."""
        return next(iter(self.all_arguments_of(name)), [])

    def all_arguments_of(self, name: str) -> list[list[str]]:
        """Return the arguments of every call to the named tool, in order."""
        return [
            line.split(" ", 1)[1].split() if " " in line else []
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.split(" ", 1)[0] == name
        ]


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

    # S603: the argument vector is this interpreter, a script path built
    # from a literal, and the test's own arguments; no shell is involved.
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
    harness.add_tool("git", stdout="README.md\0docs/guide.md\0")  # real NUL bytes
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
    # Two names split out of one NUL-delimited listing. A listing that arrived
    # as literal text would reach typos as a single argument.
    assert harness.arguments_of("uv")[-2:] == ["README.md", "docs/guide.md"], (
        f"the listing must be split on NUL: {harness.arguments_of('uv')}"
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


RENDERED_CHART = "apiVersion: v1\nkind: Service\n"
PLAN_JSON = '{"resource_changes": []}'


def _helm_arguments(harness: Harness) -> list[str]:
    """Return the arguments the fake helm was called with."""
    return harness.arguments_of("helm")


def test_helm_gate_renders_then_lints(harness: Harness) -> None:
    """helm renders the chart and yamllint reads the rendered file."""
    harness.add_tool("helm", stdout=RENDERED_CHART)
    harness.add_tool("yamllint")

    result = _run(
        "lint_helm_manifests.py",
        ["--release", "example-app", "--kube-version", "1.33.1"],
        harness,
    )

    assert result.returncode == 0, f"expected a clean exit, got {result.stderr}"
    assert harness.calls() == ["helm", "yamllint"], (
        f"the chart must be rendered before it is linted: {harness.calls()}"
    )
    arguments = _helm_arguments(harness)
    assert arguments[:2] == ["template", "example-app"], (
        f"helm must be asked to template the release: {arguments}"
    )
    assert "deploy/charts/example-app" in arguments, (
        f"the chart path must be passed: {arguments}"
    )
    assert arguments[arguments.index("--kube-version") + 1] == "1.33.1", (
        f"the requested Kubernetes version must reach helm: {arguments}"
    )
    assert harness.stdin_of("yamllint") == RENDERED_CHART.encode("utf-8"), (
        "yamllint must receive the rendered manifests, not an empty document"
    )


def test_helm_gate_reports_a_failed_render(harness: Harness) -> None:
    """A chart that fails to render never reaches yamllint."""
    harness.add_tool("helm", exit_code=1)
    harness.add_tool("yamllint")

    result = _run("lint_helm_manifests.py", [], harness)

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "helm template" in result.stderr, (
        f"the diagnostic must name the render step: {result.stderr!r}"
    )
    assert harness.calls() == ["helm"], (
        f"yamllint must not lint a failed render: {harness.calls()}"
    )


def test_helm_gate_reports_a_lint_finding(harness: Harness) -> None:
    """A yamllint finding fails the gate after a successful render."""
    harness.add_tool("helm", stdout=RENDERED_CHART)
    harness.add_tool("yamllint", exit_code=1)

    result = _run("lint_helm_manifests.py", [], harness)

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "yamllint" in result.stderr, (
        f"the diagnostic must name yamllint: {result.stderr!r}"
    )


def _flux_environment() -> dict[str, str]:
    """Return an environment that enables the Flux policy gate."""
    return {"FLUX_KUBECONFIG_PATH": "/tmp/kubeconfig"}


def test_policy_gate_plans_exports_then_checks(harness: Harness) -> None:
    """The plan is written, exported and only then checked."""
    harness.add_tool("tofu", stdout=PLAN_JSON)
    harness.add_tool("conftest")

    result = _run(
        "tofu_plan_policy.py", ["--module", "fluxcd"], harness, _flux_environment()
    )

    assert result.returncode == 0, f"expected a clean exit, got {result.stderr}"
    assert harness.calls() == ["tofu", "tofu", "conftest"], (
        f"unexpected tool order: {harness.calls()}"
    )
    plan = harness.arguments_of("tofu")
    assert plan[0] == "-chdir=infra/modules/fluxcd/examples/basic", (
        f"the plan must select the module's example: {plan}"
    )
    assert any(argument.startswith("-out=") for argument in plan), (
        f"the plan must be written to a file: {plan}"
    )
    assert "-detailed-exitcode" in plan, (
        f"the plan must report pending changes distinctly: {plan}"
    )
    assert any(argument.startswith("kubeconfig_path=") for argument in plan), (
        f"the module's variables must be passed: {plan}"
    )


def test_policy_gate_accepts_pending_changes(harness: Harness) -> None:
    """A plan reporting drift is accepted and the gate completes.

    `tofu plan -detailed-exitcode` exits 2 when changes are pending, which is
    the normal state against a live cluster. The export and the policy check
    must still run, and the gate must pass.
    """
    harness.add_tool(
        "tofu",
        by_subcommand={
            "plan": Behaviour(exit_code=2),
            "show": Behaviour(exit_code=0, stdout=PLAN_JSON),
        },
    )
    harness.add_tool("conftest")

    result = _run(
        "tofu_plan_policy.py", ["--module", "fluxcd"], harness, _flux_environment()
    )

    assert result.returncode == 0, (
        f"pending changes must not fail the gate: {result.stderr}"
    )
    assert harness.calls() == ["tofu", "tofu", "conftest"], (
        f"the accepted plan must be exported and checked: {harness.calls()}"
    )
    plan, show = harness.all_arguments_of("tofu")[:2]
    assert "-detailed-exitcode" in plan, (
        f"the plan must ask for the distinct drift status: {plan}"
    )
    assert "show" in show, f"the export must follow the accepted plan: {show}"


def test_policy_gate_stops_when_the_export_fails(harness: Harness) -> None:
    """A failed export never reaches conftest as an empty document."""
    harness.add_tool(
        "tofu",
        by_subcommand={
            "plan": Behaviour(exit_code=0),
            "show": Behaviour(exit_code=1),
        },
    )
    harness.add_tool("conftest")

    result = _run(
        "tofu_plan_policy.py", ["--module", "fluxcd"], harness, _flux_environment()
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "tofu show" in result.stderr, (
        f"the diagnostic must name the export: {result.stderr!r}"
    )
    assert harness.calls() == ["tofu", "tofu"], (
        f"conftest must not run after a failed export: {harness.calls()}"
    )


def test_policy_gate_stops_when_the_plan_fails(harness: Harness) -> None:
    """A failed plan produces no policy verdict."""
    harness.add_tool("tofu", exit_code=1)
    harness.add_tool("conftest")

    result = _run(
        "tofu_plan_policy.py", ["--module", "fluxcd"], harness, _flux_environment()
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "tofu plan" in result.stderr, (
        f"the diagnostic must name the plan: {result.stderr!r}"
    )
    assert harness.calls() == ["tofu"], (
        f"conftest must not run after a failed plan: {harness.calls()}"
    )


def test_policy_gate_reports_a_policy_violation(harness: Harness) -> None:
    """A conftest violation fails the gate and names conftest."""
    harness.add_tool("tofu", stdout=PLAN_JSON)
    harness.add_tool("conftest", exit_code=1)

    result = _run(
        "tofu_plan_policy.py", ["--module", "fluxcd"], harness, _flux_environment()
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "conftest" in result.stderr, (
        f"the diagnostic must name conftest: {result.stderr!r}"
    )


def test_policy_gate_hands_conftest_the_exported_plan(harness: Harness) -> None:
    """conftest reads the JSON the export produced."""
    harness.add_tool("tofu", stdout=PLAN_JSON)
    harness.add_tool("conftest")

    result = _run(
        "tofu_plan_policy.py", ["--module", "fluxcd"], harness, _flux_environment()
    )

    assert result.returncode == 0, f"expected a clean exit, got {result.stderr}"
    arguments = harness.arguments_of("conftest")
    assert arguments[0] == "test", f"conftest must be asked to test: {arguments}"
    assert arguments[1].endswith("plan.json"), (
        f"conftest must read the exported plan: {arguments}"
    )


def test_policy_gate_skips_when_disabled(harness: Harness) -> None:
    """A disabled gate reports a skip and runs no tool."""
    harness.add_tool("tofu")
    harness.add_tool("conftest")

    result = _run("tofu_plan_policy.py", ["--module", "fluxcd"], harness)

    assert result.returncode == 0, f"a disabled gate must pass: {result.stderr}"
    assert "Skipping fluxcd" in result.stdout, f"no skip reported: {result.stdout!r}"
    assert harness.calls() == [], "no tool may run while the gate is disabled"
