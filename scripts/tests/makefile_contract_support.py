"""Helpers for the Makefile gate contract.

A Make recipe line is handed to one shell. When that line chains commands the
shell reports only the last status, and because this Makefile does not enable
``errexit`` an earlier failure is discarded. A pipeline behaves the same way
without ``pipefail``. The helpers here read the recipes as the shell receives
them and classify each one.

``make --dry-run`` is used rather than a hand-rolled parser so the text under
test is the fully expanded command, including anything a ``$(call ...)`` macro
contributes.
"""

from __future__ import annotations

import dataclasses as dc
import functools
import re
import shutil
import subprocess
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

PHONY_PREFIX = ".PHONY:"
# Accepts `=`, `:=`, `::=`, `?=` and `+=`; only the value matters here.
SIMPLE_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?::{1,2}|\?|\+)?=\s*(.*)$")
VARIABLE_REFERENCE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)")
SET_COMMAND = "set"
PIPEFAIL_OPTION = "pipefail"


class MakeInvocationError(RuntimeError):
    """Raised when ``make --dry-run`` cannot expand a target."""


class MakeFlavourError(RuntimeError):
    """Raised when no GNU Make is available to measure the recipes with."""


def resolve_gnu_make(search_path: str | None = None) -> str:
    """Return the path of a GNU Make on ``search_path``.

    The contract reasons about GNU Make's semantics: one shell per recipe
    line, `.ONESHELL`, and `--dry-run` expansion. Another make would either
    reject the options or expand differently, so measuring with it would prove
    nothing. `gmake` is preferred because on the BSDs and macOS it is GNU Make
    while `make` is not.

    Examples
    --------
    >>> resolve_gnu_make().endswith("make")
    True
    """
    candidates = []
    for name in ("gmake", "make"):
        path = shutil.which(name, path=search_path)
        if path is None:
            continue
        reported = subprocess.run(  # noqa: S603
            [path, "--version"], capture_output=True, text=True, check=False
        )
        first_line = reported.stdout.splitlines()[0] if reported.stdout else ""
        if reported.returncode == 0 and first_line.startswith("GNU Make"):
            return path
        candidates.append(f"{path} reported {first_line!r}")

    found = "; ".join(candidates) if candidates else "no make on the search path"
    message = f"the gate contract needs GNU Make, but found: {found}"
    raise MakeFlavourError(message)


@functools.cache
def gnu_make() -> str:
    """Return the GNU Make used by the contract, resolved once.

    Examples
    --------
    >>> gnu_make() == resolve_gnu_make()
    True
    """
    return resolve_gnu_make()


class UnresolvedVariableError(RuntimeError):
    """Raised when a ``.PHONY`` declaration names a variable this cannot read.

    Expanding an unknown reference to an empty string would silently shrink
    the set of targets under contract, so it is an error instead.
    """


def _join_continuations(text: str) -> list[str]:
    """Return ``text`` with backslash-newline continuations folded together."""
    joined = re.sub(r"\\\n", " ", text)
    return joined.splitlines()


def _is_comment(line: str) -> bool:
    """Return whether the shell would treat the whole line as a comment."""
    return line.lstrip().startswith("#")


def makefile_variables(makefile: Path | None = None) -> dict[str, str]:
    """Return the Makefile's variable assignments.

    The contract builds its expected commands from these rather than
    hard-coding a version, so a pin change does not need the test edited.

    Examples
    --------
    >>> makefile_variables()["UV"]
    'uv'
    """
    makefile = makefile or (REPO_ROOT / "Makefile")
    return _simple_assignments(makefile.read_text(encoding="utf-8"))


def _simple_assignments(makefile_text: str) -> dict[str, str]:
    """Return the Makefile's top-level variable assignments."""
    assignments: dict[str, str] = {}
    for line in _join_continuations(makefile_text):
        if line.startswith((" ", "\t")):
            continue
        match = SIMPLE_ASSIGNMENT.match(line.strip())
        if match:
            assignments[match.group(1)] = match.group(2)
    return assignments


def _expand(declaration: str, assignments: dict[str, str]) -> str:
    """Substitute variable references, refusing to drop an unknown one."""

    def resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in assignments:
            message = (
                f"cannot expand ${{{name}}} in a .PHONY declaration; the "
                "contract would otherwise cover fewer targets than it claims"
            )
            raise UnresolvedVariableError(message)
        return assignments[name]

    return VARIABLE_REFERENCE.sub(resolve, declaration)


def phony_targets(makefile: Path | None = None) -> tuple[str, ...]:
    """Return every target declared ``.PHONY`` in ``makefile``.

    Variable references in a ``.PHONY`` declaration are expanded from the
    Makefile's assignments, so a target list held in a variable is covered
    too, and an unreadable reference raises rather than shrinking the set.

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
        names.extend(_expand(line[len(PHONY_PREFIX) :], assignments).split())

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
    command = [gnu_make(), "--dry-run", "--no-print-directory"]
    if makefile is not None:
        command.extend(["--file", str(makefile)])
    command.append(target)

    # S603: the argument vector is built here from literals and a target
    # name taken from the repository's own Makefile; no shell is involved.
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


@dc.dataclass(slots=True)
class _ShellScanner:
    """Tracks quoting and grouping while walking a shell command."""

    single_quoted: bool = False
    double_quoted: bool = False
    escaped: bool = False
    paren_depth: int = 0
    brace_depth: int = 0
    at_word_start: bool = True

    @property
    def at_top_level(self) -> bool:
        """Whether the next character separates two top-level commands.

        Examples
        --------
        >>> _ShellScanner().at_top_level
        True
        >>> _ShellScanner(brace_depth=1).at_top_level
        False
        """
        return not (
            self.single_quoted
            or self.double_quoted
            or self.escaped
            or self.paren_depth
            or self.brace_depth
        )

    def _advance_quoting(self, character: str) -> bool:
        """Update quote state, reporting whether it consumed the character."""
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

    def _opens_brace_group(self, character: str, follower: str) -> bool:
        """Whether the character starts a ``{ ...; }`` group."""
        return character == "{" and self.at_word_start and follower.isspace()

    def _closes_brace_group(self, character: str) -> bool:
        """Whether the character ends a ``{ ...; }`` group."""
        return character == "}" and self.at_word_start

    def _advance_grouping(self, character: str, follower: str) -> None:
        """Update subshell and brace-group depth."""
        if character == "(":
            self.paren_depth += 1
        elif character == ")":
            self.paren_depth = max(0, self.paren_depth - 1)
        elif self._opens_brace_group(character, follower):
            self.brace_depth += 1
        elif self._closes_brace_group(character):
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


def _top_level_offsets(command: str, wanted: str) -> list[int]:
    """Return offsets of ``wanted`` outside quotes and grouping constructs."""
    scanner = _ShellScanner()
    offsets: list[int] = []
    for index, character in enumerate(command):
        follower = command[index + 1] if index + 1 < len(command) else ""
        if character == wanted and scanner.at_top_level:
            offsets.append(index)
        scanner.advance(character, follower)
    return offsets


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
    return _top_level_offsets(command, ";")


def pipeline_separators(command: str) -> list[int]:
    """Return the offsets of pipes at the top level of ``command``.

    A pipeline reports only the last stage's status unless ``pipefail`` is
    set, so it discards an earlier failure exactly as a ``;`` chain does.
    ``||`` is a fail-fast list, not a pipeline, and is excluded.

    Examples
    --------
    >>> pipeline_separators("helm template chart | yamllint -")
    [20]
    >>> pipeline_separators("tofu plan || test $? -eq 2")
    []
    """
    return [
        index
        for index in _top_level_offsets(command, "|")
        if command[index - 1 : index] != "|" and command[index + 1 : index + 2] != "|"
    ]


def _set_options(command: str) -> tuple[bool, bool]:
    """Return the errexit and pipefail flags a leading ``set`` enables."""
    separators = command_separators(command)
    head = command[: separators[0]] if separators else command
    tokens = head.split()
    if not tokens or tokens[0] != SET_COMMAND:
        return (False, False)

    errexit = any(
        token.startswith("-") and not token.startswith("-o") and "e" in token[1:]
        for token in tokens[1:]
    )
    return (errexit, PIPEFAIL_OPTION in tokens[1:])


def is_guarded(command: str) -> bool:
    """Return whether ``command`` disables the hazard before chaining.

    ``errexit`` covers a ``;`` chain. A pipeline additionally needs
    ``pipefail``, because ``errexit`` alone still ignores every stage but the
    last.

    Examples
    --------
    >>> is_guarded("set -euo pipefail; helm template chart | yamllint -")
    True
    >>> is_guarded("set -eu; helm template chart | yamllint -")
    False
    >>> is_guarded("helm template chart; yamllint -")
    False
    """
    errexit, pipefail = _set_options(command)
    if not errexit:
        return False
    return pipefail or not pipeline_separators(command)


def is_single_command(command: str) -> bool:
    """Return whether ``command`` is one command rather than several.

    Examples
    --------
    >>> is_single_command("./scripts/lint_actions.py")
    True
    >>> is_single_command("if [ -d dir ]; then lint; fi")
    False
    >>> is_single_command("git ls-files | xargs typos")
    False
    """
    return not command_separators(command) and not pipeline_separators(command)


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
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as raw:
    ...     makefile = write_makefile(
    ...         Path(raw), ["yamllint f; actionlint f"], "gate"
    ...     )
    ...     recipe_lines("gate", directory=Path(raw), makefile=makefile)
    ['yamllint f; actionlint f']
    """
    body = "\n".join(f"\t{recipe}" for recipe in recipes)
    makefile = directory / "Makefile"
    makefile.write_text(
        f"SHELL := bash\n\n.PHONY: {target}\n{target}:\n{body}\n", encoding="utf-8"
    )
    return makefile
