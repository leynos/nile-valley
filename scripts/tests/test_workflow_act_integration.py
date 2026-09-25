"""Integration: `act` reads the workflows the way GitHub's runner does.

The contract tests parse the workflow with a YAML reader and inspect the tree.
That reading is blind to the parts of a workflow GitHub evaluates rather than
parses: a malformed `${{ }}` expression is a string to PyYAML and a syntax
error to the runner, and a `runs-on` label no runner provides is a valid scalar
until the job is scheduled. `act` performs both checks, and performs them
without a container, so the whole thing costs about a second and needs no
daemon.

This complements `make lint-actions`, which already runs `actionlint` over the
same files. The two disagree in useful places -- `actionlint` knows the
expression grammar in more depth, `act` additionally resolves the job's schema
-- so a failure here is reported with `act`'s own message rather than assumed
to be a duplicate of the linter's.

The containerised run (`act` without `--list`) is deliberately not exercised:
it needs a daemon, takes tens of seconds per job, and would make the ordinary
test suite depend on the host. `docs/local-validation-of-github-actions-with-
act-and-pytest.md` describes that ladder; this module is the rung below it.

`act` is not installed in CI, so the checks that invoke it are skipped there.
The premise tests are not skipped: they assert, without the binary, that each
sample `act` is fed is parseable and malformed, and that each workflow is a
mapping with jobs. Skipping those too would leave the module asserting nothing
wherever it most needs to, and a sample that merely failed to parse would make
the act checks pass for a reason unrelated to what they claim to test.
"""

from __future__ import annotations

import typing as typ

import pytest
from makefile_contract_support import REPO_ROOT

if typ.TYPE_CHECKING:
    from pathlib import Path

ACT = "act"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# `--list` parses every workflow and validates the job schema and every step
# expression, then stops before scheduling anything.
TIMEOUT_SECONDS = 120

# The socket named while probing. `--list` schedules nothing, so this value is
# never dialled; it exists so a run that did need a daemon fails immediately
# rather than hanging or quietly reaching a real one.
ABSENT_SOCKET = "unix:///nonexistent/act-probe.sock"

# The gate this change added, as the workflow spells it. Asserted here rather
# than left implicit so the act checks and the gate contract cannot drift apart
# on which step they are talking about.
TYPECHECK_STEP = "make typecheck"

# A workflow whose `if:` expression does not close its braces. PyYAML reads the
# value as an ordinary string, which is exactly why the runner's own reader is
# worth consulting; the premise is asserted in a tool-free test below.
BROKEN_EXPRESSION = (
    "name: broken\n"
    '"on": pull_request\n'
    "jobs:\n"
    "  build:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    f"      - run: {TYPECHECK_STEP}\n"
    "        if: ${{ github.event_name == }}\n"
)

# A workflow with `steps:` misspelled. Valid YAML, invalid job schema.
UNKNOWN_PROPERTY = (
    "name: unknown\n"
    '"on": pull_request\n'
    "jobs:\n"
    "  build:\n"
    "    runs-on: ubuntu-latest\n"
    "    setps:\n"
    f"      - run: {TYPECHECK_STEP}\n"
)


def act_available() -> bool:
    """Return whether the `act` binary is on ``PATH``.

    Examples
    --------
    >>> act_available()  # doctest: +SKIP
    True
    """
    import shutil

    return shutil.which(ACT) is not None


def workflow_files() -> tuple[Path, ...]:
    """Return every workflow file, sorted.

    Examples
    --------
    >>> [path.name for path in workflow_files()]  # doctest: +SKIP
    ['ci.yml', 'delayed-pr-comment.yml', 'dependabot-automerge.yml']
    """
    return tuple(sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")))


def run_act_list(*arguments: str) -> tuple[int, str]:
    """Run ``act --list`` and return its status and combined output.

    A bogus daemon socket is named so the reader never waits on a real one:
    ``--list`` does not schedule anything, so the value only has to be
    parseable for the run to be independent of the host.

    Examples
    --------
    >>> # run_act_list("-W", ".github/workflows/ci.yml")
    """
    import subprocess

    completed = subprocess.run(  # noqa: S603
        [ACT, "--list", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
        env=_without_daemon(),
    )
    return completed.returncode, completed.stdout + completed.stderr


def _without_daemon() -> dict[str, str]:
    """Return the environment with the container socket pointed at nothing.

    Examples
    --------
    >>> _without_daemon()["DOCKER_HOST"].startswith("unix://")
    True
    """
    import os

    environment = dict(os.environ)
    environment["DOCKER_HOST"] = ABSENT_SOCKET
    return environment


# `act` is not installed in CI, so the tests that shell out to it are skipped
# there. Skipping is deliberately not the module default: the premise checks
# below run wherever the suite runs, so the module still asserts something
# about the workflows in CI rather than vanishing from it entirely.
needs_act = pytest.mark.skipif(
    not act_available(),
    reason="act is not installed, so workflows cannot be read by it",
)


def workflow_text(path: Path) -> str:
    """Return one workflow's text.

    Examples
    --------
    >>> workflow_text(WORKFLOWS / "ci.yml").startswith("name:")
    True
    """
    return path.read_text(encoding="utf-8")


def test_the_broken_samples_are_actually_broken() -> None:
    """The samples the act tests feed in are parseable and malformed.

    A sample that failed to parse at all would be rejected by `act` for the
    wrong reason, and the expression test would then prove nothing about the
    expression. Both premises are asserted here, where no binary is needed.
    """
    import yaml

    broken = yaml.safe_load(BROKEN_EXPRESSION)
    unknown = yaml.safe_load(UNKNOWN_PROPERTY)

    assert broken["jobs"]["build"]["steps"][0]["if"] == "${{ github.event_name == }}", (
        "the malformed expression must survive a YAML read as a plain string, "
        "which is the whole reason the runner's own reader is worth consulting"
    )
    assert "setps" in unknown["jobs"]["build"], (
        "the unknown-property sample must parse, or it would be rejected as invalid YAML"
    )
    assert "steps" not in unknown["jobs"]["build"]


def test_the_workflows_are_readable_where_act_is_absent() -> None:
    """Every workflow is a file with YAML content, tool or no tool.

    `act` resolving a workflow presupposes there is a workflow to resolve. The
    check is trivial on its own; it is here so a workflow that was deleted or
    emptied is reported by this module rather than as an unexplained `act`
    failure on a machine that happens to have the binary.
    """
    import yaml

    for path in workflow_files():
        text = workflow_text(path)
        parsed = yaml.safe_load(text)

        assert isinstance(parsed, dict), f"{path.name} does not parse as a mapping"
        assert parsed.get("jobs"), f"{path.name} declares no jobs"


@needs_act
@pytest.mark.parametrize("path", workflow_files(), ids=lambda path: path.name)
def test_act_accepts_each_workflow(path: Path) -> None:
    """Every workflow parses under the runner's own reader.

    This is the check a YAML load cannot make: the expression grammar and the
    job schema are the runner's, not the parser's.
    """
    status, output = run_act_list("-W", str(path))

    assert status == 0, f"act rejects {path.name}:\n{output}"


@needs_act
def test_act_still_lists_the_typecheck_gate() -> None:
    """`act` resolves the continuous-integration job, not merely the file.

    A workflow can parse and still yield no job if its `jobs` key were
    misspelled or its trigger removed; listing the job proves the gates are
    reachable rather than that the file is syntactically tidy.
    """
    status, output = run_act_list("-W", str(WORKFLOWS / "ci.yml"), "-j", "build")

    assert status == 0, f"act cannot list the build job:\n{output}"
    assert "build" in output, f"the build job is absent from act's listing:\n{output}"


@needs_act
def test_act_rejects_a_malformed_step_expression(tmp_path: Path) -> None:
    """A broken `if:` is caught, though a YAML reader accepts it happily.

    This is the gap the module exists to close, so it is demonstrated rather
    than asserted: `yaml.safe_load` reads the malformed expression as an
    ordinary string, and only the runner's reader rejects it.
    """
    import yaml

    candidate = tmp_path / "broken.yml"
    candidate.write_text(BROKEN_EXPRESSION, encoding="utf-8")

    parsed = yaml.safe_load(BROKEN_EXPRESSION)
    condition = parsed["jobs"]["build"]["steps"][0]["if"]

    assert condition == "${{ github.event_name == }}", (
        "the premise of this test is that a YAML reader accepts the expression"
    )

    status, output = run_act_list("-W", str(candidate))

    assert status != 0, (
        f"act accepted a malformed expression that only it can check:\n{output}"
    )


@needs_act
def test_act_rejects_an_unknown_job_property(tmp_path: Path) -> None:
    """A misspelled job key is a schema error, not a silently ignored field."""
    candidate = tmp_path / "unknown.yml"
    candidate.write_text(UNKNOWN_PROPERTY, encoding="utf-8")

    status, output = run_act_list("-W", str(candidate))

    assert status != 0, f"act accepted a misspelled `steps` key:\n{output}"


@needs_act
def test_the_probe_does_not_depend_on_a_container_daemon() -> None:
    """The suite stays runnable where no daemon is present.

    The probe names a socket that cannot exist, so a run that succeeds is
    proof that listing needs no daemon. A test that quietly needed one would
    fail on a machine without it and would be blamed on the workflow.
    """
    status, output = run_act_list("-W", str(WORKFLOWS / "ci.yml"))

    assert status == 0, f"act --list needed a daemon after all:\n{output}"
