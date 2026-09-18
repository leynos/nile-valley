"""Where the workflows run, and which events can reach them.

Split from :mod:`scripts.tests.test_workflow_contracts`, which asks what
the jobs install and cache. These ask two questions about reachability:
which events start a run, and which runner a job lands on once one does.
No code file in this repository may exceed 400 lines, and the two sets
together did.

The rules themselves are driven twice. Each is asserted against this
repository's own workflows, which is what makes it a contract, and the
readers underneath are driven separately with declarations written to
break them, which is what makes the rule provable: a rule exercised only
against correct sources passes whether or not it works.
"""

from __future__ import annotations

import typing as typ

import pytest
from workflow_contract_support import (
    Workflow,
    iter_jobs,
    iter_steps,
    load_workflows,
    runner_labels,
)
from workflow_placement_support import (
    FORK_FIELD,
    GATE_WORKFLOW,
    GITHUB_HOSTED_LABELS,
    TRUNK_BRANCH,
    TRUNK_REFERENCE,
    UNREADABLE_RUNNER,
    build_job,
    condition_names_field,
    labels_in_expression,
    read_runner_expression,
    workflow_named,
)

#: A declaration whose condition carries a quoted literal of its own.
#: This is the event-keyed placement form the estate uses where a lane
#: serves both a pull request and a schedule, and the reader must not
#: mistake `pull_request` for a runner label.
EVENT_KEYED_DECLARATION: typ.Final = (
    "${{ github.event_name == 'pull_request'"
    " && 'ubuntu-latest' || 'ubicloud-standard-8' }}"
)


@pytest.fixture(name="workflows", scope="module")
def workflows_fixture() -> tuple[Workflow, ...]:
    """Parse every workflow document once for the whole module."""
    return load_workflows()


def test_the_gate_runs_on_trunk_as_well_as_on_a_pull_request(
    workflows: tuple[Workflow, ...],
) -> None:
    """The gate fires on a push to trunk, not only before one.

    Without it a merge that breaks the gate is invisible until somebody
    opens the next pull request, and the trunk-guarded cache saves below
    have no event that can reach them.

    Mutation: deleting the `push` trigger from `ci.yml` failed this.
    """
    gate = workflow_named(workflows, GATE_WORKFLOW)
    push = gate.triggers.get("push")

    assert "push" in gate.triggers, f"{GATE_WORKFLOW} declares no push trigger"
    assert isinstance(push, dict) and TRUNK_BRANCH in push.get("branches", []), (
        f"{GATE_WORKFLOW}'s push trigger must name {TRUNK_BRANCH}: {push!r}"
    )


def test_every_trunk_guarded_step_has_an_event_that_reaches_it(
    workflows: tuple[Workflow, ...],
) -> None:
    """A step guarded on trunk must have an automatic trigger that produces it.

    This is the contract the other two could not supply.
    `test_cache_writes_are_restricted_to_trunk` asserts each save carries
    the guard and `test_every_restored_cache_has_a_matching_save` asserts
    the keys pair, and both passed for months while `ci.yml` had no push
    trigger at all: every save was skipped on every run, the repository
    held zero cache entries, and each restore found nothing. A guard
    asserted on a step that nothing can reach is worse than no guard,
    because it reads as a mechanism.

    A `workflow_dispatch` is deliberately not counted. It can be aimed at
    trunk, so it satisfies the guard in principle, and a cache written
    only when somebody presses a button is written never.

    Mutation: deleting the `push` trigger failed this as well as the test
    above, which is the point; restoring only `workflow_dispatch`, the
    state before this branch, also failed it.
    """
    for workflow in workflows:
        guarded = [
            (job, step)
            for job, step in iter_steps((workflow,))
            if TRUNK_REFERENCE in step.condition
        ]
        if not guarded:
            continue
        assert workflow.writes_trunk_automatically(TRUNK_BRANCH), (
            f"{workflow.name} guards "
            f"{[f'{job.qualified_name}/{step.name}' for job, step in guarded]} "
            f"on {TRUNK_REFERENCE}, but declares no trigger that produces it "
            f"without a person: {sorted(workflow.triggers)}"
        )


def test_no_runner_selection_hides_a_line_break(
    workflows: tuple[Workflow, ...],
) -> None:
    """A `runs-on` expression must parse to a single line.

    A folded scalar keeps the break of a more-indented continuation, so
    the parsed value carries a newline inside the expression. GitHub
    evaluates it regardless and the job lands on the right runner, which
    is exactly why a green run proves nothing and this is read from the
    parsed document instead.

    Mutation: indenting the continuation of `build`'s `runs-on` one level
    deeper failed this.
    """
    for job in iter_jobs(workflows):
        assert "\n" not in job.raw_runs_on, (
            f"{job.qualified_name}'s runs-on carries a line break, so the "
            f"expression is split across lines: {job.raw_runs_on!r}"
        )


def test_the_gate_falls_back_to_a_hosted_runner_for_a_fork(
    workflows: tuple[Workflow, ...],
) -> None:
    """A fork's pull request must land on a GitHub-hosted runner.

    A fork cannot obtain an Ubicloud runner, so a bare Ubicloud label
    leaves the only required check unable to start and the pull request
    waiting on a job that will never be scheduled.

    The fork field is asserted by name rather than the expression being
    matched loosely, because the failure this guards against is a
    plausible sibling field in an otherwise identical expression.

    The arms are asserted by position rather than as a set. An
    expression that sends a fork to the paid runner names exactly the
    same two labels as one that does not, so "one hosted arm and one
    Ubicloud arm" is satisfied by the declaration this contract exists
    to refuse.

    Mutations: replacing `head.repo.fork` with `head.repo.private`
    failed this; so did removing the expression for a bare label, and so
    does swapping the two arms. Reading the field by substring failed
    none of them and accepted `head.repo.forked`, which is why the match
    is bounded; see `test_a_longer_field_name_is_not_the_fork_field`.
    """
    job = build_job(workflows)
    expression = read_runner_expression(job.raw_runs_on)

    assert expression is not None, (
        f"{job.qualified_name} does not select its runner by a condition "
        f"and two arms, so a fork's pull request cannot be sent elsewhere: "
        f"{job.raw_runs_on!r}"
    )
    assert condition_names_field(expression.condition, FORK_FIELD), (
        f"{job.qualified_name} must key its fallback on {FORK_FIELD}: "
        f"{expression.condition!r}"
    )
    assert expression.when_true in GITHUB_HOSTED_LABELS, (
        f"{job.qualified_name} sends a fork's pull request to "
        f"{expression.when_true!r}, which is not a GitHub-hosted runner, so "
        f"the job can never be scheduled"
    )
    assert expression.when_false not in GITHUB_HOSTED_LABELS, (
        f"{job.qualified_name} sends its own pull requests to "
        f"{expression.when_false!r}, a GitHub-hosted runner, so the fallback "
        f"buys nothing"
    )


def test_a_quoted_condition_value_is_not_read_as_a_runner() -> None:
    """A literal in the condition is not a label the job can land on.

    `runs-on: ${{ github.event_name == 'pull_request' && ... }}` is a
    valid declaration: GitHub Actions requires single quotes for string
    literals, so an event-keyed placement has no other spelling. A
    reader that gathered every quoted literal returned `pull_request`
    among the runners, and `test_non_build_jobs_stay_github_hosted`
    then rejected the declaration for naming a runner that does not
    exist.

    Driven with a declaration written here rather than with the
    repository's own, which carries no quoted condition today: a rule
    proved only by the sources it guards is proved by nothing.
    """
    labels = labels_in_expression(EVENT_KEYED_DECLARATION)

    assert labels == ("ubuntu-latest", "ubicloud-standard-8"), labels
    assert "pull_request" not in labels, (
        "a quoted value in the condition was read as a runner label"
    )


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        pytest.param(
            "${{ github.event.pull_request.head.repo.fork"
            " && 'ubuntu-latest' || 'ubicloud-standard-8' }}",
            ("ubuntu-latest", "ubicloud-standard-8"),
            id="fork-fallback",
        ),
        pytest.param(
            "${{ github.event.pull_request.head.repo.fork"
            " && 'ubicloud-standard-8' || 'ubuntu-latest' }}",
            ("ubicloud-standard-8", "ubuntu-latest"),
            id="arms-swapped",
        ),
    ],
)
def test_the_arms_are_read_by_position(
    declaration: str, expected: tuple[str, str]
) -> None:
    """The reader distinguishes the two arms, which a set cannot.

    These two declarations name the same labels and mean opposite
    things: the first sends a fork to a runner it can obtain, the second
    to one it cannot. Any contract that compares label sets accepts both.
    """
    expression = read_runner_expression(declaration)

    assert expression is not None, declaration
    assert (expression.when_true, expression.when_false) == expected


@pytest.mark.parametrize(
    ("declaration", "reason"),
    [
        pytest.param("ubuntu-latest", "a bare label", id="bare-label"),
        pytest.param(
            "${{ inputs.runner }}", "a single interpolation", id="single-value"
        ),
        pytest.param(
            "${{ github.event_name == 'push' && 'ubuntu-latest' }}",
            "one arm only",
            id="one-arm",
        ),
    ],
)
def test_a_declaration_without_two_arms_is_refused(
    declaration: str, reason: str
) -> None:
    """The reader says None rather than guessing which label was meant.

    A contract that needs to know which arm a fork takes must be able to
    tell that it cannot, instead of receiving a label chosen by position
    in a shape it does not model.
    """
    assert read_runner_expression(declaration) is None, reason


@pytest.mark.parametrize(
    ("condition", "names_it", "reason"),
    [
        pytest.param(FORK_FIELD, True, "the field alone", id="bare"),
        pytest.param(
            f"{FORK_FIELD} && github.event_name == 'pull_request'",
            True,
            "one operand of a compound condition",
            id="compound",
        ),
        pytest.param(
            f"{FORK_FIELD}ed", False, "a longer field name", id="suffixed"
        ),
        pytest.param(
            f"{FORK_FIELD}.name", False, "a field below it", id="descended"
        ),
    ],
)
def test_a_longer_field_name_is_not_the_fork_field(
    condition: str, names_it: bool, reason: str
) -> None:
    """The fallback's field is matched as a token, not as a substring.

    A substring test accepts `...head.repo.forked`, which names no field
    that GitHub defines, so the condition evaluates false and every
    fork's pull request goes to the runner a fork cannot obtain. That is
    the same failure `head.repo.private` produces, and the contract above
    exists to refuse it, so the match must reject a longer name while
    still admitting a compound condition.

    Driven against the reader with conditions written here, because this
    repository declares one condition and it is correct: a rule proved
    only by the sources it guards is proved by nothing.
    """
    assert condition_names_field(condition, FORK_FIELD) is names_it, reason


@pytest.mark.parametrize(
    "declaration",
    [
        pytest.param("${{ matrix.runner }}", id="matrix"),
        pytest.param("${{ needs.pick.outputs.runner }}", id="job-output"),
        pytest.param("${{ vars.RUNNER }}", id="variable"),
    ],
)
def test_an_unreadable_expression_is_not_read_as_no_runner(declaration: str) -> None:
    """A `runs-on` this reader cannot follow must fail the contracts, not skip them.

    `test_non_build_jobs_stay_github_hosted` and the registry contract
    both skip a job that declares no runner, which is right for a job
    that calls a reusable workflow. An expression naming its runner
    somewhere this reader does not follow returned nothing at all and
    took the same path, so the job passed every placement contract by
    being unreadable. The reader returns a sentinel instead, which is in
    no hosted set and in no registry, so those contracts refuse it.

    Mutation: returning an empty tuple for these declarations failed
    this test.
    """
    labels = runner_labels(declaration)

    assert labels == (UNREADABLE_RUNNER,), labels
    assert UNREADABLE_RUNNER not in GITHUB_HOSTED_LABELS, (
        "the sentinel must not be admitted as a GitHub-hosted runner"
    )
