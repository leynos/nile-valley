"""Property tests for the placement and reachability readers.

The parametrized cases cover the forms someone thought to write down. These
cover the forms nobody did: a condition carrying its own quoted literal or its
own `&&`, any combination of the triggers that cannot reach trunk, a branch
named in either filter, and a `runs-on` in each of the three shapes GitHub
Actions accepts.

Each declaration is assembled from parts whose meaning is known by
construction, so the expected answer is recorded while the string is built
rather than recomputed by a second implementation of the rule. A property that
derived its expectation by parsing would agree with the parser about
everything, including its mistakes.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st
from workflow_contract_support import Workflow, branch_filter_admits, runner_labels
from workflow_placement_support import (
    labels_in_expression,
    read_runner_expression,
)

#: A runner label. Constrained away from the quote and the operators,
#: because a label carrying either is not a label GitHub would accept
#: and the generated declaration would no longer mean what it records.
LABEL = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-."),
    min_size=1,
    max_size=20,
)

#: A branch name, and the patterns a filter may hold.
BRANCH = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-/"),
    min_size=1,
    max_size=12,
)

#: A condition. Three shapes, each a real one: a bare field, a field
#: compared against a quoted literal, and two of those joined by `&&`.
#: The second and third are what the label reader used to get wrong.
CONDITION = st.one_of(
    st.just("github.event.pull_request.head.repo.fork"),
    st.just("github.event_name == 'pull_request'"),
    st.just("github.event_name == 'push' && github.ref == 'refs/heads/main'"),
)


def _ternary(condition: str, when_true: str, when_false: str) -> str:
    """Build the short-circuit declaration GitHub uses for a ternary."""
    return f"${{{{ {condition} && '{when_true}' || '{when_false}' }}}}"


@given(condition=CONDITION, when_true=LABEL, when_false=LABEL)
def test_the_arms_read_back_in_the_order_they_were_written(
    condition: str, when_true: str, when_false: str
) -> None:
    """A declaration built from two arms reads back as those two arms.

    Stated as a round trip because the failure it guards against is a
    reader that returns the right pair in the wrong order. A test
    comparing sets would hold for the swap, which is the whole defect.
    """
    declaration = _ternary(condition, when_true, when_false)
    expression = read_runner_expression(declaration)

    assert expression is not None, f"unread: {declaration!r}"
    assert (expression.when_true, expression.when_false) == (when_true, when_false), (
        f"{declaration!r} read back as "
        f"{(expression.when_true, expression.when_false)!r}"
    )


@given(condition=CONDITION, when_true=LABEL, when_false=LABEL)
def test_a_quoted_condition_value_is_never_a_label(
    condition: str, when_true: str, when_false: str
) -> None:
    """Only the operands of the result operators are labels.

    Two of the three generated conditions carry a quoted literal of
    their own, and the third carries two along with its own `&&`. A
    reader that gathered every quoted literal returned those as runners,
    and the registry contract then rejected a valid declaration.
    """
    declaration = _ternary(condition, when_true, when_false)
    labels = labels_in_expression(declaration)

    assert labels == (when_true, when_false), (
        f"{declaration!r} yielded {labels!r} rather than its two arms"
    )


@given(
    condition=CONDITION,
    when_true=LABEL,
    when_false=LABEL,
    spaces=st.integers(min_value=1, max_value=6),
)
def test_the_spacing_does_not_change_which_arm_is_which(
    condition: str, when_true: str, when_false: str, spaces: int
) -> None:
    """Whitespace around the operators must not change the reading.

    A folded scalar whose continuation keeps the opening indent joins
    its lines with a space, and this repository's own declaration is
    written across three lines, so the reader meets padded forms in
    practice. It must not depend on the spacing, or the line-break
    contract would be separating two cases the reader already confuses.
    """
    padded = _ternary(condition, when_true, when_false).replace(" ", " " * spaces)
    expression = read_runner_expression(padded)

    assert expression is not None, f"unread at {spaces} spaces: {padded!r}"
    assert (expression.when_true, expression.when_false) == (when_true, when_false), (
        f"{padded!r} read back as "
        f"{(expression.when_true, expression.when_false)!r}"
    )


@given(branch=BRANCH, others=st.lists(BRANCH, max_size=4))
def test_an_ignored_branch_is_refused_however_it_is_listed(
    branch: str, others: list[str]
) -> None:
    """`branches-ignore` naming the branch refuses it, always.

    Whatever else the filter holds. A push that ignores trunk starts no
    run for a push to trunk, and the reader that consulted `branches`
    alone reported such a workflow as reaching trunk automatically.
    """
    event = {"branches-ignore": [*others, branch]}

    assert branch_filter_admits(event, branch) is False, (
        f"{branch!r} was admitted although {event!r} ignores it"
    )


@given(branch=BRANCH, others=st.lists(BRANCH, max_size=4))
def test_a_branch_outside_the_named_set_is_refused(
    branch: str, others: list[str]
) -> None:
    """A `branches` list that does not name the branch refuses it."""
    listed = [other for other in others if other != branch]

    assert branch_filter_admits({"branches": listed}, branch) is False, (
        f"{branch!r} was admitted although branches names only {listed!r}"
    )


@given(branch=BRANCH, others=st.lists(BRANCH, max_size=4))
def test_a_named_branch_with_no_exclusion_is_admitted(
    branch: str, others: list[str]
) -> None:
    """Naming the branch and excluding nothing admits it."""
    listed = [*others, branch]

    assert branch_filter_admits({"branches": listed}, branch) is True, (
        f"{branch!r} was refused although branches names it: {listed!r}"
    )


@given(branch=BRANCH, others=st.lists(BRANCH, max_size=4))
def test_a_later_pattern_overrides_an_earlier_one(
    branch: str, others: list[str]
) -> None:
    """Order decides the answer, in both directions.

    GitHub reads a `branches` list in sequence: a matching `!` entry
    after a positive match excludes the ref, and a matching positive
    entry after that includes it again. A reader that asked whether any
    pattern matched read the exclusion as an admission, and a gate whose
    filter deliberately excludes trunk was then reported as reaching
    trunk automatically.
    """
    admitting = [*others, branch]
    excluded = [*admitting, f"!{branch}"]
    readmitted = [*excluded, branch]

    assert branch_filter_admits({"branches": excluded}, branch) is False, (
        f"{branch!r} survived the exclusion that follows it in {excluded!r}"
    )
    assert branch_filter_admits({"branches": readmitted}, branch) is True, (
        f"{branch!r} stayed excluded although {readmitted!r} names it last"
    )


@given(
    branch=BRANCH,
    triggers=st.lists(
        st.sampled_from(["pull_request", "workflow_dispatch", "issue_comment"]),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
def test_no_manual_or_pull_request_trigger_reaches_trunk(
    branch: str, triggers: list[str]
) -> None:
    """Only a push or a schedule produces the trunk ref unaided.

    A `workflow_dispatch` can be aimed at trunk and so satisfies a guard
    in principle, which is exactly why it is excluded: a cache written
    only when somebody presses a button is written never. Stated over
    every combination of the manual and pull-request triggers rather
    than the one this repository declares today.
    """
    workflow = Workflow(
        name="generated.yml",
        path=Path("generated.yml"),
        triggers=dict.fromkeys(triggers),
        jobs=(),
    )

    assert workflow.writes_trunk_automatically(branch) is False, (
        f"{sorted(triggers)} was read as producing {branch!r} unaided"
    )


@given(labels=st.lists(LABEL, min_size=1, max_size=3, unique=True))
def test_every_runs_on_shape_yields_the_labels_it_names(labels: list[str]) -> None:
    """GitHub accepts three shapes, and all three name runners.

    A scalar, a sequence, and a mapping with `group` and `labels`.
    Treating any of them as absent would leave a job with no labels,
    and a placement contract that sees no labels asserts nothing at all,
    which is how a self-hosted job slips past one.
    """
    sequence = tuple(labels)
    first = (labels[0],)
    group = {"group": "ubuntu runners", "labels": labels}
    group_scalar = {"group": "ubuntu runners", "labels": labels[0]}

    assert runner_labels(labels[0]) == first, f"scalar {labels[0]!r}"
    assert runner_labels(labels) == sequence, f"sequence {labels!r}"
    assert runner_labels(group) == sequence, f"group mapping {group!r}"
    assert runner_labels(group_scalar) == first, f"group mapping {group_scalar!r}"


@given(condition=CONDITION, when_true=LABEL, when_false=LABEL)
def test_an_expression_runs_on_yields_its_arms_and_nothing_else(
    condition: str, when_true: str, when_false: str
) -> None:
    """The scalar shape carrying an expression yields the two arms.

    The same question as the label reader's, asked through the shape a
    job actually declares, because that is the path the placement
    contracts take.
    """
    declaration = _ternary(condition, when_true, when_false)

    assert runner_labels(declaration) == (when_true, when_false), (
        f"{declaration!r} yielded {runner_labels(declaration)!r}"
    )
