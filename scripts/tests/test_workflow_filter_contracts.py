"""How a branch filter is read, and which branches it admits.

Split from :mod:`scripts.tests.test_workflow_placement_contracts`, which
asks which runner a job lands on once a run starts. These ask the prior
question: whether an event's `branches` and `branches-ignore` keys let a
given branch start one at all. That answer decides whether a
trunk-guarded step has anything that can reach it, so the grammar is
GitHub's rather than a near neighbour's.

Every case is driven against the reader with a filter written here. No
document in this repository uses a pattern at all, so a rule exercised
only over the repository's own filters would pass whether or not it
worked.
"""

from __future__ import annotations

import pytest
from workflow_contract_support import branch_filter_admits
from workflow_placement_support import TRUNK_BRANCH


@pytest.mark.parametrize(
    ("pattern", "branch", "admitted", "reason"),
    [
        pytest.param("release/*", "release/a", True, "one segment", id="single"),
        pytest.param(
            "release/*", "release/a/b", False, "two segments", id="star-stops-at-slash"
        ),
        pytest.param("release/**", "release/a/b", True, "any depth", id="doublestar"),
        pytest.param("main", "main", True, "an exact name", id="exact"),
        pytest.param("main?", "main", True, "the last character present", id="opt-on"),
        pytest.param("main?", "mai", True, "the last character absent", id="opt-off"),
        pytest.param(
            "main?", "mains", False, "a character the pattern never names", id="opt-not-any"
        ),
        pytest.param("mai+n", "main", True, "one occurrence", id="plus-one"),
        pytest.param("mai+n", "maiiin", True, "three occurrences", id="plus-many"),
        pytest.param("mai+n", "man", False, "no occurrence", id="plus-none"),
        pytest.param("m[ai]n", "man", True, "a listed member", id="class-member"),
        pytest.param("m[ai]n", "men", False, "an unlisted member", id="class-outsider"),
        pytest.param("v[0-9]", "v7", True, "a range", id="class-range"),
        pytest.param(
            "m[a/b]n", "m[a/b]n", True, "not a class GitHub reads", id="class-literal"
        ),
    ],
)
def test_a_filter_pattern_is_read_as_github_reads_it(
    pattern: str, branch: str, admitted: bool, reason: str
) -> None:
    """GitHub's glob, in full: `*`, `**`, `?`, `+`, and a bracket class.

    `fnmatch` gets the first of those wrong, and the direction of the
    error is what matters. It matches `release/*` against `release/a/b`,
    so a workflow whose push filter does not admit trunk was reported as
    reaching trunk automatically, and the reachability contract passed
    on exactly the workflow it exists to fail.

    The quantifiers were wrong in the other direction. `?` binds to the
    character before it and stands for zero or one of that character,
    and `+` for one or more; read as "any one character" instead,
    `main?` admitted `mains` and refused `main`. Brackets were escaped
    rather than read, so `m[ai]n` refused `man`. Each mistake reads a
    filter as covering a set of branches that it does not, which is how
    a reachability answer comes out wrong.

    Mutations: restoring `?` to `[^/]`, restoring `+` to `[^/]+`, and
    escaping the brackets each failed a case here.
    """
    assert branch_filter_admits({"branches": [pattern]}, branch) is admitted, reason


@pytest.mark.parametrize(
    ("event", "admitted", "reason"),
    [
        pytest.param({"branches": ["main"]}, True, "named", id="named"),
        pytest.param({}, True, "no filter at all", id="unfiltered"),
        pytest.param(
            {"branches": ["release/**"]}, False, "not matched", id="other-branch"
        ),
        pytest.param({"branches-ignore": ["main"]}, False, "excluded", id="ignored"),
        pytest.param(
            {"branches-ignore": ["release/**"]},
            True,
            "excluded elsewhere",
            id="ignored-elsewhere",
        ),
    ],
)
def test_a_branch_filter_is_read_both_ways(
    event: dict[str, object], admitted: bool, reason: str
) -> None:
    """`branches-ignore` excludes as surely as `branches` admits.

    A `push` that ignores trunk starts no run for a push to trunk, so a
    reader that consulted `branches` alone reported such a workflow as
    reaching trunk automatically and would have accepted trunk-guarded
    steps that nothing can reach. That is the same defect the
    reachability contract exists to catch, arriving through the reader
    instead of through the workflow.
    """
    assert branch_filter_admits(event, TRUNK_BRANCH) is admitted, reason


@pytest.mark.parametrize(
    ("patterns", "admitted", "reason"),
    [
        pytest.param(["**"], True, "one admitting pattern", id="admitted"),
        pytest.param(["**", "!main"], False, "excluded after", id="excluded-after"),
        pytest.param(["!main", "**"], True, "admitted after", id="readmitted-after"),
        pytest.param(
            ["**", "!main", "ma?in"],
            True,
            "re-included by a later positive",
            id="reincluded"
        ),
        pytest.param(
            ["**", "!release/**"], True, "excluded elsewhere", id="exclusion-misses"
        ),
        pytest.param(["!main"], False, "excluded with nothing admitting", id="only-negative"),
    ],
)
def test_the_order_of_the_patterns_decides_the_answer(
    patterns: list[str], admitted: bool, reason: str
) -> None:
    """A later pattern overrides an earlier one, in either direction.

    GitHub evaluates a `branches` list in the order it is written: a
    matching `!` entry after a positive match excludes the ref, and a
    matching positive entry after that includes it again. A reader that
    asked whether any pattern matched read `["**", "!main"]` as
    admitting `main`, so a gate whose push filter deliberately excludes
    trunk was reported as reaching it, and its trunk-guarded cache saves
    passed the reachability contract while no run could ever execute
    them. That is the same shape of failure the push trigger on this
    branch exists to fix, reached through the reader.

    Mutation: restoring the `any(...)` reading failed the two exclusion
    cases here and left every other case passing.
    """
    assert branch_filter_admits({"branches": patterns}, TRUNK_BRANCH) is admitted, reason
