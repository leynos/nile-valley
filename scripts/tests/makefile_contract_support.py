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

import dataclasses as dc
import re
import subprocess
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

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
    >>> recipe_lines("lint-actions")[0].endswith("scripts/lint_actions.py")
    True
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


@dc.dataclass
class _ShellScanner:
    """Tracks quoting and grouping while walking a shell command.

    Only a semicolon that is unquoted, unescaped and outside every grouping
    construct separates two top-level commands.
    """

    single_quoted: bool = False
    double_quoted: bool = False
    escaped: bool = False
    paren_depth: int = 0
    brace_depth: int = 0
    at_word_start: bool = True

    @property
    def at_top_level(self) -> bool:
        """Whether the next character sits between two top-level commands."""
        return not (
            self.single_quoted
            or self.double_quoted
            or self.escaped
            or self.paren_depth
            or self.brace_depth
        )

    def _advance_quoting(self, character: str) -> bool:
        """Update quote state, reporting whether it consumed ``character``."""
        if self.escaped:
            self.escaped = False
            return True
        if character == "\\":
            self.escaped = True
            return True
        if self.single_quoted:
            self.single_quoted = character != "'"
            return True
        if self.double_quoted:
            self.double_quoted = character != '"'
            return True
        if character in "'\"":
            self.single_quoted = character == "'"
            self.double_quoted = character == '"'
            return True
        return False

    def _advance_grouping(self, character: str, follower: str) -> None:
        """Update subshell and brace-group depth."""
        if character == "(":
            self.paren_depth += 1
        elif character == ")":
            self.paren_depth = max(0, self.paren_depth - 1)
        elif character == "{" and self.at_word_start and follower.isspace():
            self.brace_depth += 1
        elif character == "}" and self.at_word_start:
            self.brace_depth = max(0, self.brace_depth - 1)

    def advance(self, character: str, follower: str) -> None:
        """Consume one character of the command.

        Examples
        --------
        >>> scanner = _ShellScanner()
        >>> scanner.advance("'", "a")
        >>> scanner.at_top_level
        False
        """
        if not self._advance_quoting(character):
            self._advance_grouping(character, follower)
        self.at_word_start = character in " \t;&|("


def command_separators(command: str) -> list[int]:
    """Return the offsets of ``;`` separators at the top level of ``command``.

    Semicolons inside quotes, a ``$(...)`` substitution, a subshell or a
    ``{ ...; }`` group are not separators between top-level commands, and a
    ``&&`` or ``||`` list already stops at the first failure.

    Examples
    --------
    >>> command_separators("yamllint file; actionlint file")
    [13]
    >>> command_separators("command -v tool || { echo missing; exit 1; }")
    []
    """
    scanner = _ShellScanner()
    offsets: list[int] = []
    for index, character in enumerate(command):
        follower = command[index + 1] if index + 1 < len(command) else ""
        if character == ";" and scanner.at_top_level:
            offsets.append(index)
        scanner.advance(character, follower)
    return offsets


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
