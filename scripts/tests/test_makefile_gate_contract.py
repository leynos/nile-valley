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
import subprocess
import typing as typ

import pytest
from makefile_contract_support import (
    REPO_ROOT,
    MakeFlavourError,
    gnu_make,
    ignored_failure_lines,
    resolve_gnu_make,
    makefile_variables,
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

# `uv` may be named by an absolute path, and two recipes prefix the launcher
# with environment assignments; the Makefile's `UV ?= uv` also takes the value
# of an inherited `UV` variable, which `uv run` itself sets.
UV_RUN = re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S* )*(?:\S*/)?uv run ")

VARIABLES = makefile_variables()


def _gate_command(template: str) -> str:
    """Fill a Makefile variable into an expected gate command."""
    return template.format(**VARIABLES)


# The whole invocation is stated, not just the script name. A contract that
# matched only the prefix would certify `... --help`, which lints nothing.
CONVERTED_GATES = {
    "lint-actions": "scripts/lint_actions.py",
    "yamllint": "scripts/lint_helm_manifests.py --kube-version {KUBE_VERSION}",
    "check-fmt": (
        "scripts/run_bun_tool.py --tool biome "
        "--package @biomejs/biome@{BIOME_VERSION} "
        "-- ci --formatter-enabled=true --reporter=github scripts"
    ),
    "markdownlint": (
        "scripts/run_bun_tool.py --tool markdownlint-cli2 "
        "--package markdownlint-cli2@{MARKDOWNLINT_CLI2_VERSION} -- '**/*.md'"
    ),
    "spelling": "scripts/check_spelling.py --typos-version {TYPOS_VERSION}",
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
    """Return the recipe lines that run exactly ``command`` under ``uv run``."""
    # The remainder has to match in full. Accepting a prefix would let a
    # neutralized invocation such as a trailing `--help` satisfy the contract.
    expected = _gate_command(command)
    matches = []
    for line in lines:
        launcher = UV_RUN.match(line)
        if launcher is None:
            continue
        if line[launcher.end() :] == expected:
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
    """The recipe runs the gate script, with exactly the arguments it needs."""
    lines = recipe_lines(target)
    assert _invocations(lines, command), (
        f"{target} must run `uv run {_gate_command(command)}`; recipe is {lines}"
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


@pytest.mark.parametrize(
    ("target", "command"), sorted(CONVERTED_GATES.items()), ids=str
)
def test_a_neutralized_invocation_is_rejected(target: str, command: str) -> None:
    """A contract that matched a prefix would certify a gate that runs nothing.

    Appending an option that makes the script exit without linting keeps the
    script name in the recipe, so the check has to compare the whole command.
    """
    neutralized = [f"uv run {_gate_command(command)} --help"]

    assert _invocations(neutralized, command) == [], (
        f"{target} would be certified by a neutralized invocation"
    )


def _fake_make(directory: Path, name: str, version_line: str) -> Path:
    """Install a fake make that reports ``version_line`` for ``--version``."""
    script = directory / name
    script.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{version_line}'\n", encoding="utf-8"
    )
    script.chmod(0o755)
    return script


def test_the_contract_measures_with_gnu_make() -> None:
    """The recipes are read with the make whose semantics they are read under.

    One shell per recipe line, `.ONESHELL` and `--dry-run` expansion are GNU
    Make behaviours; another make would expand differently or reject the
    options, so measuring with it would prove nothing.
    """
    reported = subprocess.run(  # noqa: S603
        [gnu_make(), "--version"], capture_output=True, text=True, check=False
    )

    assert reported.stdout.startswith("GNU Make"), (
        f"{gnu_make()} is not GNU Make: {reported.stdout.splitlines()[:1]}"
    )


def test_a_non_gnu_make_is_rejected(tmp_path: Path) -> None:
    """A search path offering only another make fails loudly."""
    _fake_make(tmp_path, "make", "bmake version 20240101")

    with pytest.raises(MakeFlavourError, match="needs GNU Make") as excinfo:
        resolve_gnu_make(search_path=str(tmp_path))

    assert "bmake" in str(excinfo.value), (
        f"the error must name what it found: {excinfo.value}"
    )


def test_gmake_is_preferred_over_make(tmp_path: Path) -> None:
    """On a platform where `make` is not GNU Make, `gmake` usually is."""
    _fake_make(tmp_path, "make", "bmake version 20240101")
    expected = _fake_make(tmp_path, "gmake", "GNU Make 4.4.1")

    assert resolve_gnu_make(search_path=str(tmp_path)) == str(expected), (
        "the resolver must prefer gmake when make is another implementation"
    )


def test_no_recipe_ignores_a_failure() -> None:
    """A leading `-` tells Make to disregard the exit status.

    It is the Make-native `|| true`, and `make --dry-run` strips it before
    printing, so the recipe text is read instead of the expansion.
    """
    offenders = ignored_failure_lines()

    assert offenders == [], f"these recipes ignore their exit status: {offenders}"


def test_the_ignored_failure_check_reads_the_prefix(tmp_path: Path) -> None:
    """The check finds the prefix in any order and ignores continuations."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "gate:\n"
        "\t@-uv run scripts/lint_actions.py\n"
        "\tuv run scripts/check_spelling.py \\\n"
        "\t-not-a-prefix\n",
        encoding="utf-8",
    )

    offenders = ignored_failure_lines(makefile)

    assert offenders == ["@-uv run scripts/lint_actions.py"], (
        f"expected only the prefixed line, got {offenders}"
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
