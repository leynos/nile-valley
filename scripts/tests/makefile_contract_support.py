"""Helpers for the Makefile gate contract.

A Make recipe line is handed to one shell. When that line chains commands the
shell reports only the last status, and because this Makefile does not enable
``errexit`` an earlier failure is discarded. The helpers here read the
recipes as the shell receives them and classify each one.

``make --dry-run`` is used rather than a hand-rolled parser so the text under
test is the fully expanded command, including anything a ``$(call ...)`` macro
contributes.
"""

from __future__ import annotations

import re
import subprocess
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

# A line beginning with `set -e` enables errexit for the rest of that shell,
# so any chain after it stops at the first failure.
ERREXIT_PREFIX = re.compile(r"^set\s+-[a-zA-Z]*e")

PHONY_PREFIX = ".PHONY:"
SIMPLE_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:?=\s*(.*)$")
VARIABLE_REFERENCE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)")


class MakeInvocationError(RuntimeError):
    """Raised when ``make --dry-run`` cannot expand a target."""


def _join_continuations(text: str) -> list[str]:
    """Return ``text`` with backslash-newline continuations folded together."""
    joined = re.sub(r"\\\n", " ", text)
    return joined.splitlines()


def _is_comment(line: str) -> bool:
    """Return whether the shell would treat the whole line as a comment."""
    return line.lstrip().startswith("#")


def _simple_assignments(makefile_text: str) -> dict[str, str]:
    """Return the Makefile's simple variable assignments."""
    assignments: dict[str, str] = {}
    for line in _join_continuations(makefile_text):
        if line.startswith((" ", "\t")) or ":" not in line:
            continue
        match = SIMPLE_ASSIGNMENT.match(line.strip())
        if match:
            assignments[match.group(1)] = match.group(2)
    return assignments


def phony_targets(makefile: Path | None = None) -> tuple[str, ...]:
    """Return every target declared ``.PHONY`` in ``makefile``.

    Variable references in a ``.PHONY`` declaration are expanded from the
    Makefile's simple assignments, so a target list held in a variable is
    covered too.

    Examples
    --------
    >>> "lint-actions" in phony_targets()
    True
    """
    makefile = makefile or (REPO_ROOT / "Makefile")
    text = makefile.read_text(encoding="utf-8")
    assignments = _simple_assignments(text)

    names: list[str] = []
    for line in _join_continuations(text):
        if not line.startswith(PHONY_PREFIX):
            continue
        declaration = line[len(PHONY_PREFIX) :]
        declaration = VARIABLE_REFERENCE.sub(
            lambda match: assignments.get(match.group(1), ""), declaration
        )
        names.extend(declaration.split())

    return tuple(dict.fromkeys(names))


def recipe_lines(
    target: str, *, directory: Path | None = None, makefile: Path | None = None
) -> list[str]:
    """Return the shell commands Make would run for ``target``.

    Examples
    --------
    >>> recipe_lines("lint-actions")
    ['./scripts/lint_actions.py']
    """
    directory = directory or REPO_ROOT
    command = ["make", "--dry-run", "--no-print-directory"]
    if makefile is not None:
        command.extend(["--file", str(makefile)])
    command.append(target)

    completed = subprocess.run(  # noqa: S603
        command, cwd=directory, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        message = (
            f"make --dry-run {target} exited {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
        raise MakeInvocationError(message)

    return [
        line.strip()
        for line in _join_continuations(completed.stdout)
        if line.strip() and not _is_comment(line)
    ]


def _quote_and_group_state(command: str) -> Iterator[tuple[int, str, int, int, bool]]:
    """Yield ``(index, character, paren depth, brace depth, quoted)`` per byte."""
    paren_depth = 0
    brace_depth = 0
    single = False
    double = False
    escaped = False
    at_word_start = True

    for index, character in enumerate(command):
        quoted = single or double
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif single:
            single = character != "'"
        elif double:
            double = character != '"'
        elif character == "'":
            single = True
        elif character == '"':
            double = True
        elif character == "(":
            paren_depth += 1
        elif character == ")":
            paren_depth = max(0, paren_depth - 1)
        elif (
            character == "{"
            and at_word_start
            and index + 1 < len(command)
            and command[index + 1].isspace()
        ):
            brace_depth += 1
        elif character == "}" and at_word_start:
            brace_depth = max(0, brace_depth - 1)

        yield index, character, paren_depth, brace_depth, quoted
        at_word_start = character in " \t;&|("


def command_separators(command: str) -> list[int]:
    """Return the offsets of ``;`` separators at the top level of ``command``.

    Semicolons inside quotes, a ``$(...)`` substitution, a subshell or a
    ``{ ...; }`` group are not separators between top-level commands, and a
    ``&&`` or ``||`` list already stops at the first failure.

    Examples
    --------
    >>> command_separators("yamllint file; actionlint file")
    [15]
    >>> command_separators("command -v tool || { echo missing; exit 1; }")
    []
    """
    return [
        index
        for index, character, paren, brace, quoted in _quote_and_group_state(command)
        if character == ";" and not quoted and paren == 0 and brace == 0
    ]


def is_guarded(command: str) -> bool:
    """Return whether ``command`` enables ``errexit`` before chaining.

    Examples
    --------
    >>> is_guarded("set -euo pipefail; helm template chart | yamllint -")
    True
    >>> is_guarded("helm template chart; yamllint -")
    False
    """
    return bool(ERREXIT_PREFIX.match(command.strip()))


def is_single_command(command: str) -> bool:
    """Return whether ``command`` is one command rather than a chain.

    Examples
    --------
    >>> is_single_command("./scripts/lint_actions.py")
    True
    >>> is_single_command("if [ -d dir ]; then lint; fi")
    False
    """
    return not command_separators(command)


def offending_lines(targets: Iterable[str]) -> dict[str, list[str]]:
    """Return, per target, the recipe lines that are neither single nor guarded.

    Examples
    --------
    >>> offending_lines(["lint-actions"])
    {}
    """
    offenders: dict[str, list[str]] = {}
    for target in targets:
        bad = [
            line
            for line in recipe_lines(target)
            if not is_single_command(line) and not is_guarded(line)
        ]
        if bad:
            offenders[target] = bad
    return offenders


def write_makefile(directory: Path, recipes: Sequence[str], target: str) -> Path:
    """Write a one-target Makefile used to prove the contract can fail.

    Examples
    --------
    >>> # write_makefile(tmp_path, ["yamllint f; actionlint f"], "gate")
    """
    body = "\n".join(f"\t{recipe}" for recipe in recipes)
    makefile = directory / "Makefile"
    makefile.write_text(f"SHELL := bash\n\n.PHONY: {target}\n{target}:\n{body}\n")
    return makefile
