"""Contract: no Make recipe may chain gate commands in one shell.

This Makefile sets neither ``.ONESHELL`` nor an ``errexit`` shell flag, so a
recipe line that chains commands with ``;`` reports only the last status and
an earlier failure is discarded. Every recipe line must therefore be a single
command, or must enable ``errexit`` before it chains.

The final test mutates a Makefile to re-introduce a chain and asserts the
contract rejects it, so a contract that has stopped checking anything cannot
pass unnoticed.
"""

from __future__ import annotations

import re
import typing as typ

import pytest
from makefile_contract_support import (
    REPO_ROOT,
    command_separators,
    is_guarded,
    is_single_command,
    offending_lines,
    phony_targets,
    recipe_lines,
    write_makefile,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

# `uv` may be named by an absolute path: the Makefile's `UV ?= uv` takes the
# value of an inherited `UV` environment variable, which `uv run` itself sets.
UV_RUN = re.compile(r"^(?:\S*/)?uv run ")

# The gate scripts each replaced a chained recipe; the recipe must invoke the
# script through `uv run`, not merely mention it.
CONVERTED_GATES = {
    "lint-actions": "scripts/lint_actions.py",
    "yamllint": "scripts/lint_helm_manifests.py",
    "check-fmt": "scripts/run_bun_tool.py",
    "fluxcd-policy": "scripts/tofu_plan_policy.py --module fluxcd",
    "traefik-policy": "scripts/tofu_plan_policy.py --module traefik",
    "external-dns-policy": "scripts/tofu_plan_policy.py --module external-dns",
    "cert-manager-policy": "scripts/tofu_plan_policy.py --module cert-manager",
    "vault-eso-policy": "scripts/tofu_plan_policy.py --module vault-eso",
}

# Targets whose examples are validated and planned by the shared gate script.
EXAMPLE_GATE_TARGETS = {
    "fluxcd-test": "scripts/tofu_example_gate.py --module fluxcd",
    "traefik-test": "scripts/tofu_example_gate.py --module traefik",
    "external-dns-test": "scripts/tofu_example_gate.py --module external-dns",
    "cert-manager-test": "scripts/tofu_example_gate.py --module cert-manager",
    "vault-eso-test": "scripts/tofu_example_gate.py --module vault-eso",
}


def _invocations(lines: list[str], command: str) -> list[str]:
    """Return the recipe lines that run ``command`` under ``uv run``."""
    # Matching the launcher and then the remainder of the line keeps the
    # assertion tied to the invocation, not a mention inside an argument.
    matches = []
    for line in lines:
        launcher = UV_RUN.match(line)
        if launcher is None:
            continue
        remainder = line[launcher.end() :]
        if remainder == command or remainder.startswith(f"{command} "):
            matches.append(line)
    return matches


@pytest.mark.parametrize("target", phony_targets(), ids=str)
def test_every_recipe_line_is_a_single_or_guarded_command(target: str) -> None:
    """No phony target chains commands in an unguarded shell."""
    offenders = [
        line
        for line in recipe_lines(target)
        if not is_single_command(line) and not is_guarded(line)
    ]
    assert offenders == [], f"{target} chains commands: {offenders}"


@pytest.mark.parametrize(
    ("target", "command"), sorted(CONVERTED_GATES.items()), ids=str
)
def test_converted_gate_invokes_its_script(target: str, command: str) -> None:
    """The recipe runs the gate script as a command of its own."""
    lines = recipe_lines(target)
    assert _invocations(lines, command), (
        f"{target} must run `uv run {command}`; recipe is {lines}"
    )


@pytest.mark.parametrize(
    ("target", "command"), sorted(EXAMPLE_GATE_TARGETS.items()), ids=str
)
def test_example_gate_targets_validate_and_plan_through_the_script(
    target: str, command: str
) -> None:
    """Validation and planning run from one command per module."""
    lines = recipe_lines(target)
    assert len(_invocations(lines, command)) == 1, (
        f"{target} must run `uv run {command}` exactly once; recipe is {lines}"
    )


def test_the_makefile_defines_no_oneshell() -> None:
    """The per-line shell is what makes an unguarded chain dangerous.

    Adding ``.ONESHELL`` would extend the hazard to whole recipes, so the
    contract records its absence rather than assuming it.
    """
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert ".ONESHELL" not in text, (
        "with .ONESHELL a whole recipe shares one shell, widening the hazard"
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param("scripts/lint_actions.py", True, id="single-command"),
        pytest.param("cd dir && tflint --init && tflint", True, id="and-list"),
        pytest.param("tofu plan || test $? -eq 2", True, id="or-guard"),
        pytest.param(
            'command -v tool >/dev/null || { echo "missing"; exit 1; }',
            True,
            id="brace-group-guard",
        ),
        pytest.param('echo "one; two"', True, id="semicolon-in-quotes"),
        pytest.param("sh -c 'a; b'", True, id="semicolon-in-single-quotes"),
        pytest.param("yamllint files; actionlint files", False, id="chain"),
        pytest.param("if [ -d dir ]; then lint; fi", False, id="conditional"),
        pytest.param("for f in *; do lint $f; done", False, id="loop"),
        pytest.param("helm template chart | yamllint -", False, id="pipeline"),
        pytest.param("git ls-files -z | xargs -0 typos", False, id="xargs-pipeline"),
    ],
)
def test_classifier_recognizes_command_shapes(
    command: str, *, expected: bool
) -> None:
    """A chain is distinguished from a fail-fast list or a quoted semicolon."""
    assert is_single_command(command) is expected, (
        f"{command!r} should{'' if expected else ' not'} be a single command"
    )


def test_errexit_prefix_is_treated_as_guarded() -> None:
    """A chain preceded by `set -e` stops at the first failure."""
    chained = "set -euo pipefail; helm template chart | yamllint -"
    assert not is_single_command(chained), "the line still chains two commands"
    assert is_guarded(chained), "errexit with pipefail covers a pipeline"
    assert not is_guarded("set -eu; helm template chart | yamllint -"), (
        "errexit alone still ignores every pipeline stage but the last"
    )
    assert not is_guarded("helm template chart; yamllint -"), (
        "an unprefixed chain is not guarded"
    )


def test_separator_offsets_point_at_the_chain() -> None:
    """The reported offset is the separator, which makes failures readable."""
    command = "yamllint file; actionlint file"
    assert command_separators(command) == [command.index(";")], (
        f"the separator offset must locate the chain in {command!r}"
    )


def test_contract_rejects_a_reintroduced_chain(tmp_path: Path) -> None:
    """Mutation proof: putting the chain back makes the contract fail.

    The mutated recipe is the shape the repository had before this change,
    where yamllint's status was discarded and actionlint decided the gate.
    """
    target = "lint-actions"
    chained = (
        "find .github/workflows -name '*.yml' -print0 | xargs -0 -r yamllint; \\\n"
        "\tfind .github/workflows -name '*.yml' -print0 | xargs -0 -r actionlint"
    )
    makefile = write_makefile(tmp_path, [chained], target)

    lines = recipe_lines(target, directory=tmp_path, makefile=makefile)

    assert len(lines) == 1, f"the continuation must fold into one line: {lines}"
    assert not is_single_command(lines[0]), (
        "the re-introduced chain must be recognized as several commands"
    )
    assert not is_guarded(lines[0]), "the chain enables no errexit guard"


def test_repository_has_no_offending_targets() -> None:
    """The whole Makefile is clean, not merely the targets listed above."""
    offenders = offending_lines(phony_targets())
    assert offenders == {}, f"these recipes chain commands: {offenders}"
