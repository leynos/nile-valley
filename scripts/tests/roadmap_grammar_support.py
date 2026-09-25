"""The roadmap heading grammar, and readers for the document that uses it.

`docs/ephemeral-previews-roadmap.md` is parsed by `mapsplice`, whose grammar
is not documented anywhere in this repository. It was recovered by probing the
tool:

- A phase is ``## N. Title``: a bare integer, a literal dot, then the title.
  A status suffix such as ``(To do)`` is accepted after the title.
- A step is ``### N.M. Title``, and the phase part must equal the number of
  the enclosing phase. A step under the wrong phase is rejected.
- Numbering need not be sequential or gap-free, and the order of phases and
  steps is not checked.
- ``## Phase N: Title`` and ``### N.M: Title`` are rejected. Those are the
  forms this document used before it was aligned with the grammar.

Everything here reads text and needs nothing installed, so the contract it
backs runs wherever the suite runs. The patterns are the grammar restated, and
restating it cannot show that it is what the tool enforces, so
:mod:`scripts.tests.mapsplice_support` probes the real binary and the tests
put the two readings side by side.
"""

from __future__ import annotations

import re
import typing as typ
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROADMAP_PATH = REPO_ROOT / "docs" / "ephemeral-previews-roadmap.md"

# `## N. Title`, with an optional `(Status)` suffix. The dot is what separates
# this from the rejected `## Phase 1. Title` and `## 1 Title` forms, and the
# title must be non-empty so a bare `## 1.` is not read as a phase.
PHASE = re.compile(r"^##[ \t]+(?P<number>\d+)\.(?P<rest>[ \t]+\S.*?)?[ \t]*$")

# `### N.M. Title`. Both dots are required: `### 1.1: Title` is rejected as an
# "unsupported non-roadmap heading" and `### 1.1 Title` likewise.
STEP = re.compile(
    r"^###[ \t]+(?P<phase>\d+)\.(?P<step>\d+)\.(?P<rest>[ \t]+\S.*?)?[ \t]*$"
)

# Any heading that tries to be a phase or a step. Used to catch the forms the
# two patterns above do not claim, rather than only the two known-legacy ones.
# The tool rejects a stray heading at any depth below the title -- `#### 1.1.`
# is as unrecognised to it as `## 1 Not a phase` -- so the pattern is not
# limited to the two canonical levels. The level-one document title is outside
# the grammar's scope and is deliberately left alone.
HEADING = re.compile(r"^(?P<hashes>#{2,})[ \t]")

# The forms this document used before it was aligned. Both are written so they
# cannot match a canonical heading: `LEGACY_PHASE` requires the literal word
# `Phase`, and `LEGACY_STEP` requires a colon or a space where the canonical
# second dot must be, so `### 2.1. Title` is never mistaken for a legacy step.
LEGACY_PHASE = re.compile(r"^##[ \t]+Phase[ \t]+\d+[.:]")
LEGACY_STEP = re.compile(r"^###[ \t]+\d+\.\d+[ \t:]")


@dataclass(frozen=True)
class Phase:
    """One phase heading.

    Attributes
    ----------
    number:
        The phase's own number, from ``## N.``.
    title:
        The title text, including any status suffix.
    line:
        The 1-based line the heading appears on, for a readable failure.
    """

    number: int
    title: str
    line: int


@dataclass(frozen=True)
class Step:
    """One step heading, tied to the phase that encloses it.

    Attributes
    ----------
    phase:
        The phase number this step belongs to, from ``N.M.``.
    number:
        The step's own number, from ``N.M.``.
    title:
        The title text, including any status suffix.
    line:
        The 1-based line the heading appears on.
    """

    phase: int
    number: int
    title: str
    line: int

    @property
    def dotted(self) -> str:
        """Return the step's number in the document's own notation.

        Examples
        --------
        >>> # Step(2, 3, "Core cluster services", 54).dotted
        >>> # '2.3'
        """
        return f"{self.phase}.{self.number}"


def read(path: Path | None = None) -> str:
    """Return the roadmap's text.

    Examples
    --------
    >>> read().startswith("# Ephemeral previews infrastructure roadmap")
    True
    """
    return (path or ROADMAP_PATH).read_text(encoding="utf-8")


def body_lines(text: str) -> typ.Iterator[tuple[int, str]]:
    """Yield ``(line number, line)`` for lines outside fenced code blocks.

    A future task that quotes a heading inside a fenced example would
    otherwise be read as a real heading, which would fail the contract on a
    document the tool accepts.

    Examples
    --------
    >>> list(body_lines("a\\n```\\n## 1. X\\n```\\nb\\n"))
    [(1, 'a'), (5, 'b')]
    """
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield number, line


_Row = typ.TypeVar("_Row")


def _title(match: re.Match[str]) -> str:
    """Return the title text a phase or step match carries.

    Both readers pull the same trailing text out of their own match, and a
    status suffix is part of that title for both.

    Examples
    --------
    >>> _title(PHASE.match("## 1. A (To do)"))
    'A (To do)'
    """
    return (match.group("rest") or "").strip()


def _rows(
    text: str,
    pattern: re.Pattern[str],
    build: typ.Callable[[int, re.Match[str]], _Row],
) -> tuple[_Row, ...]:
    """Return one built row per body heading ``pattern`` matches.

    Both readers walk the body for their own heading form and build a frozen
    dataclass per match, so the walk and the build live here rather than once
    in each of them. Keeping the build in the caller's own function is what
    leaves each reader naming its own fields.

    Examples
    --------
    >>> _rows("## 1. A\\n", PHASE, _phase_row)
    (Phase(number=1, title='A', line=1),)
    """
    return tuple(
        build(number, match)
        for number, line in body_lines(text)
        if (match := pattern.match(line)) is not None
    )


def _phase_row(number: int, match: re.Match[str]) -> Phase:
    """Build the phase a ``PHASE`` match describes."""
    return Phase(number=int(match.group("number")), title=_title(match), line=number)


def _step_row(number: int, match: re.Match[str]) -> Step:
    """Build the step a ``STEP`` match describes."""
    return Step(
        phase=int(match.group("phase")),
        number=int(match.group("step")),
        title=_title(match),
        line=number,
    )


def phases(text: str) -> tuple[Phase, ...]:
    """Return every phase heading, in document order.

    Examples
    --------
    >>> [phase.number for phase in phases(read())]
    [1, 2, 3, 4]
    """
    return _rows(text, PHASE, _phase_row)


def steps(text: str) -> tuple[Step, ...]:
    """Return every step heading, in document order.

    Examples
    --------
    >>> [step.dotted for step in steps(read())][:2]
    ['2.1', '2.2']
    """
    return _rows(text, STEP, _step_row)


def _offending(
    text: str, predicate: typ.Callable[[str], bool], label: str = ""
) -> tuple[str, ...]:
    """Return a located report for each body line ``predicate`` selects.

    The two readers below ask the same question -- which lines are wrong, and
    where -- and differ only in what makes a line wrong and in the words put in
    front of it, so the walk and the location live here.

    Examples
    --------
    >>> _offending("## 1. A\\n", lambda line: line.startswith("## 1"))
    ('line 1: ## 1. A',)
    >>> _offending("## 1. A\\n", lambda line: line.startswith("## 1"), "bad ")
    ('line 1: bad ## 1. A',)
    """
    return tuple(
        f"line {number}: {label}{line.strip()}"
        for number, line in body_lines(text)
        if predicate(line)
    )


def _is_legacy(line: str) -> bool:
    """Return whether ``line`` is a heading in one of the rejected forms.

    Examples
    --------
    >>> _is_legacy("## Phase 1: Legacy"), _is_legacy("## 1. Fine")
    (True, False)
    """
    if LEGACY_PHASE.match(line) is not None:
        return True
    return LEGACY_STEP.match(line) is not None


def _is_unrecognized(line: str) -> bool:
    """Return whether ``line`` is a heading that is neither a phase nor a step.

    Examples
    --------
    >>> _is_unrecognized("#### 1.1. B"), _is_unrecognized("### 1.1. B")
    (True, False)
    """
    if HEADING.match(line) is None:
        return False
    return PHASE.match(line) is None and STEP.match(line) is None


def legacy_headings(text: str) -> tuple[str, ...]:
    """Return every heading still written in a form the tool rejects.

    Examples
    --------
    >>> legacy_headings("# T\\n\\n## 1. Fine\\n")
    ()
    >>> legacy_headings("## Phase 1: Legacy")[0].startswith("line 1")
    True
    """
    return _offending(text, _is_legacy)


def unrecognized_headings(text: str) -> tuple[str, ...]:
    """Return every heading that is not a phase or a step, with its line.

    This is the tool's own rule, which rejects any heading inside the roadmap
    body that is neither a phase nor a step. It catches the legacy forms and
    everything else, including a level the grammar has no room for.

    Examples
    --------
    >>> unrecognized_headings(read())
    ()
    >>> unrecognized_headings("## Phase 1: Legacy")
    ('line 1: unsupported heading ## Phase 1: Legacy',)
    """
    return _offending(text, _is_unrecognized, "unsupported heading ")


def problems(text: str) -> tuple[str, ...]:
    """Return every reason ``text`` is not a well-formed roadmap fragment.

    This is the grammar read off the patterns alone, with no dependency on the
    `mapsplice` binary. It exists so the contract still refuses the rejected
    forms on a machine where the tool is absent -- which is every machine that
    runs the ordinary suite in CI.

    Two readings are checked against each other where the tool *is* present:
    this one must accept every form the tool accepts and refuse every form it
    refuses. A reader that could only ever return an empty tuple, or only ever
    complain, would fail one half of that comparison. The comparison lives in
    :mod:`scripts.tests.mapsplice_support`.

    The rules are the tool's, and no more:

    - Every heading inside the body is a phase or a step.
    - A step names a phase the document declares.
    - A step sits under the phase it names.

    Numbering is deliberately not checked for being sequential or gap-free,
    and phases and steps are not required to be ordered, because the tool
    accepts both. Adding such a rule here would make this reader stricter than
    the grammar it mirrors, and the cross-check would then fail on a document
    the tool is content with.

    Examples
    --------
    >>> problems("## 1. A\\n\\n### 1.1. B\\n")
    ()
    >>> problems("## Phase 1: Legacy")
    ('line 1: unsupported heading ## Phase 1: Legacy',)
    >>> problems("## 2. A\\n\\n### 1.1. B\\n")
    ('line 3: step 1.1 names undeclared phase 1',)
    """
    found = list(unrecognized_headings(text))

    declared = {phase.number for phase in phases(text)}
    current: int | None = None
    for number, line in body_lines(text):
        if (phase := PHASE.match(line)) is not None:
            current = int(phase.group("number"))
            continue
        step = STEP.match(line)
        if step is None:
            continue
        names, sits_under = int(step.group("phase")), current
        if names not in declared:
            found.append(
                f"line {number}: step {names}.{step.group('step')} "
                f"names undeclared phase {names}"
            )
        elif sits_under != names:
            found.append(
                f"line {number}: step {names}.{step.group('step')} "
                f"sits under phase {sits_under}"
            )
    return tuple(found)


def fragment(text: str) -> str:
    """Return ``text`` from its first phase heading onward.

    `mapsplice` refuses a fragment that opens with prose, so the front matter
    is dropped, as the validating invocation does. When no canonical phase is
    present the first heading of any form is used instead, so the tool reports
    its own complaint about the heading rather than an empty fragment.

    Examples
    --------
    >>> fragment("# T\\n\\nintro\\n\\n## 1. A\\n").startswith("## 1. A")
    True
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if PHASE.match(line.rstrip("\n")):
            return "".join(lines[index:])
    for index, line in enumerate(lines):
        if HEADING.match(line.rstrip("\n")):
            return "".join(lines[index:])
    return ""
