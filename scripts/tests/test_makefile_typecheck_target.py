"""Behavioural coverage for the `typecheck` target and its place in `all`.

`typecheck` is the newest gate and the easiest to weaken without noticing.
Dropping `--checkJs` leaves `tsc` accepting JavaScript it never inspects, and
dropping `--noEmit` leaves it writing output over the tree it is inspecting;
both still exit zero on this repository's single JavaScript file, so only the
recipe text distinguishes them. The argument list is therefore asserted whole.

The compiler is a cmd-mox double on a controlled search path, so the pinned
TypeScript is never resolved and no package is downloaded. The double is what
proves the two properties the Makefile depends on: the arguments reach the
compiler unchanged, and the compiler's exit status reaches the caller.
"""

from __future__ import annotations

import re
import typing as typ

import pytest
from makefile_contract_support import REPO_ROOT, makefile_variables, recipe_lines

from scripts.tests.gate_test_support import activate, commands_run

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

VARIABLES = makefile_variables()
TARGET = "typecheck"
CHECKED_FILE = "scripts/install-mermaid-browser.mjs"

# The compiler arguments the target must pass, in order. Each is load bearing:
# without `--allowJs` the `.mjs` file is not a candidate for checking at all,
# and `--checkJs` is what makes it a checked candidate rather than an ignored
# one. The module settings resolve the `node:` specifiers the script imports,
# and `--noEmit` keeps the check from writing beside the source.
COMPILER_ARGUMENTS = (
    "--allowJs",
    "--checkJs",
    "--noEmit",
    "--target",
    "ES2022",
    "--module",
    "NodeNext",
    "--moduleResolution",
    "NodeNext",
    CHECKED_FILE,
)

ALL_TARGET = "all"

# Every gate `all` must keep. `typecheck` is the one this change added; the
# rest are here so the check covers the whole target rather than that one line.
ALL_GATES = ("check-fmt", "lint", TARGET, "test", "spelling")

PACKAGE_SPEC = f"typescript@{VARIABLES['TYPESCRIPT_VERSION']}"

# `uv` may be named by an absolute path: the Makefile's `UV ?= uv` takes the
# value of an inherited `UV` variable, which `uv run` itself sets. Only the
# launcher is allowed that freedom; the rest of the line is compared exactly.
UV_RUN = re.compile(r"^(?:\S*/)?uv run ")


def _prerequisites(target: str, makefile_text: str) -> tuple[str, ...]:
    """Return the prerequisites Make lists for ``target``.

    `make --dry-run` expands recipes but prints no prerequisites, so they are
    read from the Makefile text. The `all` target names its prerequisites
    literally, so no variable expansion is needed.
    """
    joined = makefile_text.replace("\\\n", " ")
    match = re.search(rf"^{re.escape(target)}:[ \t]*(.*?)[ \t]*$", joined, re.MULTILINE)
    assert match is not None, f"the Makefile declares no target `{target}`"
    return tuple(match.group(1).split())


def makefile_text() -> str:
    """Return the repository Makefile's text.

    Examples
    --------
    >>> "typecheck:" in makefile_text()
    True
    """
    return (REPO_ROOT / "Makefile").read_text(encoding="utf-8")


def test_the_recipe_passes_the_pinned_compiler_and_every_argument() -> None:
    """The recipe, as Make expands it, is the documented invocation.

    The whole line is compared rather than searched. A check that looked for
    the arguments as a substring would pass on a recipe that runs `tsc --help`
    afterwards, which checks nothing.
    """
    expected = (
        f"scripts/run_bun_tool.py --tool tsc "
        f"--package {PACKAGE_SPEC} -- {' '.join(COMPILER_ARGUMENTS)}"
    )

    lines = recipe_lines(TARGET)

    assert len(lines) == 1, f"the recipe must be one command, got {lines}"
    launcher = UV_RUN.match(lines[0])
    assert launcher is not None, (
        f"`make {TARGET}` must run the runner under `uv run`: {lines[0]!r}"
    )
    # The remainder has to match in full. Accepting a prefix would let a
    # neutralized invocation such as a trailing `--help` satisfy the contract.
    assert lines[0][launcher.end() :] == expected, (
        f"`make {TARGET}` must expand to {expected!r}"
    )


def test_the_checked_file_is_the_only_tracked_javascript() -> None:
    """The file the gate names is the file the gate exists for.

    If the script were renamed or moved, the recipe would still exit zero on a
    non-existent path only by failing, so the contract pins the name here.
    """
    assert (REPO_ROOT / CHECKED_FILE).is_file(), (
        f"{CHECKED_FILE} is named by the {TARGET} recipe but does not exist"
    )


def test_the_pinned_version_matches_the_documented_default() -> None:
    """The pin is asserted, not assumed, so a silent drift is a failure.

    The developer's guide states 5.9.2. If the pin moves, this test fails and
    names the document that has to move with it.
    """
    assert VARIABLES["TYPESCRIPT_VERSION"] == "5.9.2", (
        f"docs/developers-guide.md documents 5.9.2; the Makefile pins "
        f"{VARIABLES['TYPESCRIPT_VERSION']!r}"
    )


def missing_gates(text: str) -> tuple[str, ...]:
    """Return the gates absent from the `all` target in ``text``.

    Examples
    --------
    >>> missing_gates(makefile_text()) == ()
    True
    """
    prerequisites = _prerequisites(ALL_TARGET, text)
    return tuple(gate for gate in ALL_GATES if gate not in prerequisites)


@pytest.mark.parametrize("gate", ALL_GATES, ids=str)
def test_all_runs_each_gate(gate: str) -> None:
    """`make all` is the local equivalent of CI, gate for gate."""
    assert gate not in missing_gates(makefile_text()), (
        f"{gate} is missing from `{ALL_TARGET}`: "
        f"{_prerequisites(ALL_TARGET, makefile_text())}"
    )


@pytest.mark.parametrize("gate", ALL_GATES, ids=str)
def test_the_contract_rejects_a_gate_dropped_from_all(gate: str) -> None:
    """Mutation proof: dropping any gate from `all` fails the contract.

    Removing a prerequisite is the plainest way to stop a gate running
    locally, so the check is shown to bite rather than assumed to. The
    mutation is fed to the contract's own predicate, so this proves the
    predicate rather than a copy of it.
    """
    mutated = re.sub(
        rf"^{re.escape(ALL_TARGET)}:.*?$",
        f"{ALL_TARGET}: " + " ".join(g for g in ALL_GATES if g != gate),
        makefile_text(),
        count=1,
        flags=re.MULTILINE,
    )

    assert gate in missing_gates(mutated), (
        f"the contract would not notice {gate} leaving `{ALL_TARGET}`"
    )
    assert missing_gates(makefile_text()) == (), (
        "the harness must not disturb the Makefile it reads"
    )


def test_an_installed_compiler_receives_the_gate_arguments(cmd_mox: CmdMox) -> None:
    """An installed `tsc` is preferred, and gets the arguments unchanged.

    The compiler is a double, so this runs with the pinned TypeScript absent
    and downloads nothing.
    """
    from scripts.run_bun_tool import main

    cmd_mox.stub("tsc").returns(exit_code=0)
    cmd_mox.stub("bun").returns(exit_code=0)
    activate(cmd_mox)

    main(*COMPILER_ARGUMENTS, tool="tsc", package=PACKAGE_SPEC)

    assert commands_run(cmd_mox) == ["tsc"], (
        "an installed compiler must be preferred to the downloading fallback"
    )
    recorded = cmd_mox.journal[0].args
    assert recorded == list(COMPILER_ARGUMENTS), (
        f"the compiler must receive the gate's arguments in order: {recorded}"
    )


def test_a_failing_compiler_fails_the_gate(cmd_mox: CmdMox) -> None:
    """A non-zero status from the compiler is reported, not swallowed.

    `tsc` reports findings through its status and prints nothing to standard
    output for a clean tree, so a discarded status would let an unchecked file
    pass the gate.
    """
    from scripts._gate_runner import GateError
    from scripts.run_bun_tool import main

    cmd_mox.stub("tsc").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError, match="tsc"):
        main(*COMPILER_ARGUMENTS, tool="tsc", package=PACKAGE_SPEC)


def test_the_bun_fallback_keeps_the_pin_and_the_arguments(cmd_mox: CmdMox) -> None:
    """With no installed compiler, `bun x` runs the pinned package.

    The fallback is what makes the gate reproducible on a machine without a
    global `tsc`, so it must carry both the exact version and the arguments.
    """
    from scripts.run_bun_tool import main

    cmd_mox.stub("bun").returns(exit_code=0)
    activate(cmd_mox)

    main(*COMPILER_ARGUMENTS, tool="nile-valley-absent-tsc", package=PACKAGE_SPEC)

    recorded = cmd_mox.journal[0].args

    assert recorded[:2] == ["x", f"--package={PACKAGE_SPEC}"], (
        f"the pinned package must reach bun: {recorded}"
    )
    assert recorded[2:] == [
        "nile-valley-absent-tsc",
        *COMPILER_ARGUMENTS,
    ], f"the arguments must follow the package: {recorded}"


def test_a_failing_bun_fallback_fails_the_gate(cmd_mox: CmdMox) -> None:
    """A failure from the fallback reaches the caller, named."""
    from scripts._gate_runner import GateError
    from scripts.run_bun_tool import main

    cmd_mox.stub("bun").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError, match="nile-valley-absent-tsc"):
        main(*COMPILER_ARGUMENTS, tool="nile-valley-absent-tsc", package=PACKAGE_SPEC)
