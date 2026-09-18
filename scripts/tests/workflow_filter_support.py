"""How GitHub reads a branch filter, and which branches one admits.

Split from :mod:`scripts.tests.workflow_contract_support`, which loads the
workflow documents and knows what a job declares. This module answers the
prior question: whether an event's `branches` and `branches-ignore` keys
let a given branch start a run at all. That answer decides whether a
trunk-guarded step has any event that can reach it, so the grammar has to
be GitHub's rather than a near neighbour's.

The reader takes a pattern and a branch name rather than a document, so a
contract can drive it with a filter written for the purpose. No workflow
here uses a pattern at all, and a rule exercised only over the
repository's own filters passes whether or not it works.

Examples
--------
>>> branch_filter_admits({"branches": ["release/**"]}, "release/a/b")
True
>>> branch_filter_admits({"branches": ["**", "!main"]}, "main")
False
"""

from __future__ import annotations

import re
import typing as typ

__all__ = ["branch_filter_admits"]


_CLASS_MEMBER: typ.Final = re.compile(r"[A-Za-z0-9-]+\Z")


def _read_character_class(pattern: str, index: int) -> tuple[str, int] | None:
    """Return the regex for a bracket class at ``index``, and the index after it.

    None means the brackets are not a class GitHub documents, so the
    caller reads the `[` literally rather than guessing at a meaning.
    GitHub's class holds alphanumerics and ranges of them and nothing
    else, so a bracket carrying anything further is a branch name that
    happens to contain a bracket.

    Parameters
    ----------
    pattern : str
        The whole filter pattern.
    index : int
        The offset of the opening bracket.

    Returns
    -------
    tuple[str, int] or None
        The class and the offset after its closing bracket, or None.

    Examples
    --------
    >>> _read_character_class("m[ai]n", 1)
    ('[ai]', 5)
    >>> _read_character_class("m[a/b]n", 1) is None
    True
    >>> _read_character_class("m[ain", 1) is None
    True
    """
    close = pattern.find("]", index + 1)
    if close == -1:
        return None
    members = pattern[index + 1 : close]
    if not _CLASS_MEMBER.match(members):
        return None
    return f"[{members}]", close + 1


def _quantify(parts: list[str], quantifier: str) -> None:
    """Apply ``quantifier`` to the last atom emitted, or emit it literally.

    GitHub's `?` and `+` bind to the character before them rather than
    standing for one character and for one or more. With nothing before
    them there is nothing to repeat, so the character is a literal.

    Parameters
    ----------
    parts : list[str]
        The regex fragments built so far, modified in place.
    quantifier : str
        Either `?` or `+`.

    Examples
    --------
    >>> parts = ["a"]
    >>> _quantify(parts, "?")
    >>> parts
    ['(?:a)?']
    >>> parts = []
    >>> _quantify(parts, "+")
    >>> parts
    ['\\\\+']
    """
    if not parts:
        parts.append(re.escape(quantifier))
        return
    parts[-1] = f"(?:{parts[-1]}){quantifier}"


def _read_atom(pattern: str, index: int) -> tuple[str, int]:
    """Return the regex for the atom at ``index``, and the index after it.

    An atom is everything a quantifier can bind to: an escaped
    character, `**`, `*`, a bracket class, or one literal character. A
    bracket that is not a class GitHub reads is one literal character,
    which is why the fallthrough is shared rather than repeated.

    Parameters
    ----------
    pattern : str
        The whole filter pattern.
    index : int
        The offset to read from.

    Returns
    -------
    tuple[str, int]
        The regex fragment and the offset after it.

    Examples
    --------
    >>> _read_atom("**/x", 0)
    ('.*', 2)
    >>> _read_atom("*/x", 0)
    ('[^/]*', 1)
    >>> _read_atom(r"\\*x", 0)
    ('\\\\*', 2)
    >>> _read_atom("m[ai]n", 1)
    ('[ai]', 5)
    """
    char = pattern[index]
    if char == "\\" and index + 1 < len(pattern):
        return re.escape(pattern[index + 1]), index + 2
    if pattern.startswith("**", index):
        return ".*", index + 2
    if char == "*":
        return "[^/]*", index + 1
    if char == "[":
        member_class = _read_character_class(pattern, index)
        if member_class is not None:
            return member_class
    return re.escape(char), index + 1


def _filter_pattern(pattern: str) -> re.Pattern[str]:
    """Return ``pattern`` as GitHub reads a branch filter.

    `fnmatch` is not a stand-in for this, and the comment that said it
    was had the direction of harm backwards. GitHub's `*` matches
    within a path segment and its `**` crosses `/`; `fnmatch`'s `*`
    crosses `/` always. So `fnmatch` matches `release/*` against
    `release/a/b` where GitHub does not, and the reader then reported a
    workflow as reaching trunk automatically when no push to trunk
    would start a run. That is a reachability contract passing on
    exactly the workflow it exists to fail, which is the opposite of
    the "errs towards admitting" claim that was written here.

    The rest of the grammar is GitHub's own: `?` matches zero or one of
    the preceding character and `+` one or more of it, so both bind to
    what came before rather than standing for a character of their own;
    `[]` is a class of alphanumerics and ranges; and `\\` escapes the
    character after it. An earlier reading treated `?` as exactly one
    character and escaped the brackets, so `main?` admitted `mains` and
    refused `main`, and `m[ai]n` refused `man`: each the wrong way
    round, and each a branch filter read as covering a set of branches
    that it does not.

    Parameters
    ----------
    pattern : str
        A `branches` or `branches-ignore` entry, without any leading `!`.

    Returns
    -------
    re.Pattern[str]
        A pattern anchored at both ends.

    Examples
    --------
    >>> bool(_filter_pattern("release/*").fullmatch("release/a"))
    True
    >>> bool(_filter_pattern("release/*").fullmatch("release/a/b"))
    False
    >>> bool(_filter_pattern("release/**").fullmatch("release/a/b"))
    True
    >>> bool(_filter_pattern("mai?n").fullmatch("main"))
    True
    >>> bool(_filter_pattern("mai+n").fullmatch("maiin"))
    True
    >>> bool(_filter_pattern("m[ai]n").fullmatch("man"))
    True
    >>> bool(_filter_pattern("m[ai]n").fullmatch("main"))
    False
    """
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern[index] in "?+":
            _quantify(parts, pattern[index])
            index += 1
            continue
        fragment, index = _read_atom(pattern, index)
        parts.append(fragment)
    return re.compile("".join(parts))


def _last_verdict(branch: str, patterns: object) -> bool | None:
    """Return the verdict of the last pattern ``branch`` matches, or None.

    GitHub evaluates a filter in the order it is written: a later `!`
    pattern excludes a branch an earlier one admitted, and a later
    positive pattern admits it again. Reporting "any pattern matches"
    instead read `["**", "!main"]` as admitting `main`, so a workflow
    whose push filter excludes trunk was reported as reaching trunk
    automatically and its trunk-guarded cache saves passed the
    reachability contract while nothing could run them.

    None means no pattern matched at all, which the caller reads
    differently for the two filter keys.

    Parameters
    ----------
    branch : str
        A branch's short name.
    patterns : object
        The raw value of a `branches` or `branches-ignore` key.

    Returns
    -------
    bool or None
        Whether the last matching pattern admits, or None if none match.

    Examples
    --------
    >>> _last_verdict("main", ["main"])
    True
    >>> _last_verdict("main", ["**", "!main"])
    False
    >>> _last_verdict("main", ["**", "!main", "main"])
    True
    >>> _last_verdict("main", ["releases/**"]) is None
    True
    >>> _last_verdict("main", "main") is None
    True
    """
    if not isinstance(patterns, list):
        return None
    verdict: bool | None = None
    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        admits = not pattern.startswith("!")
        expression = pattern if admits else pattern[1:]
        if _filter_pattern(expression).fullmatch(branch) is not None:
            verdict = admits
    return verdict


def branch_filter_admits(event: dict[str, object], branch: str) -> bool:
    """Report whether an event's branch filters let ``branch`` start a run.

    Both filters are read, because either alone decides the question.
    `branches-ignore` excludes outright: a `push` that ignores `main`
    starts no run for a push to `main`, however the rest of the trigger
    is written, and reading only `branches` reported such a workflow as
    reaching trunk automatically. `branches` restricts: present, it is
    the whole admitted set; absent, every branch is admitted.

    GitHub refuses a workflow that declares both filters for one event,
    so the two cannot disagree in a document that runs at all.

    The patterns are read as GitHub reads them rather than through
    `fnmatch`; see `_filter_pattern` for why that difference decides a
    contract rather than a corner case. Within one key they are read in
    order, so a later `!` entry excludes what an earlier entry admitted;
    see `_last_verdict`.

    Parameters
    ----------
    event : dict[str, object]
        The mapping under a trigger such as `push`.
    branch : str
        The branch's short name.

    Returns
    -------
    bool
        Whether a push to ``branch`` starts a run.

    Examples
    --------
    >>> branch_filter_admits({"branches": ["main"]}, "main")
    True
    >>> branch_filter_admits({"branches-ignore": ["main"]}, "main")
    False
    >>> branch_filter_admits({}, "main")
    True
    >>> branch_filter_admits({"branches": ["**", "!main"]}, "main")
    False
    >>> branch_filter_admits({"branches": ["**", "!main", "ma?in"]}, "main")
    True
    """
    if _last_verdict(branch, event.get("branches-ignore")) is True:
        return False
    branches = event.get("branches")
    if branches is None:
        return True
    return _last_verdict(branch, branches) is True
