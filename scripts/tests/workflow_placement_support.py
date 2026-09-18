"""The repository's placement rules, and the reader that checks them.

Two things live here: the facts the placement and trigger contracts
assert about this repository, and the reader that turns a ``runs-on``
expression into the runners it can select.

Split from :mod:`scripts.tests.workflow_contract_support`, which loads the
workflow documents. The reader here takes a string rather than a document,
so a contract can drive it with a declaration written for the purpose. A
rule exercised only against the repository's own workflows can fail on a
regression and on nothing else, which means a mutation that removes it
survives.

A placement expression has one shape across the estate::

    ${{ <condition> && '<when true>' || '<when false>' }}

GitHub Actions has no ternary operator; this is the short-circuit idiom that
stands in for one. Which arm is which matters, so the arms are read by
position rather than gathered into a set: an expression that sends a fork's
pull request to a paid runner names exactly the same two labels as one that
does not.

Examples
--------
>>> expression = read_runner_expression(
...     "${{ github.event.pull_request.head.repo.fork"
...     " && 'ubuntu-latest' || 'ubicloud-standard-8' }}"
... )
>>> expression.when_true
'ubuntu-latest'
>>> expression.when_false
'ubicloud-standard-8'
>>> labels_in_expression(
...     "${{ github.event_name == 'pull_request'"
...     " && 'ubuntu-latest' || 'ubicloud-standard-8' }}"
... )
('ubuntu-latest', 'ubicloud-standard-8')
"""

from __future__ import annotations

import dataclasses as dc
import re
import typing as typ

if typ.TYPE_CHECKING:
    from workflow_contract_support import Job, Workflow

#: A quoted literal that follows a result operator. A placement
#: expression names the labels it can select as the operands of `&&` and
#: `||`; a quoted literal anywhere else is part of the condition. The
#: distinction is not cosmetic: `github.event_name == 'pull_request'` is
#: a perfectly ordinary condition, and reading its operand as a label
#: reported `pull_request` as an unregistered runner and failed the
#: placement contract on a valid declaration.
_RESULT_ARM: typ.Final = re.compile(r"(?:&&|\|\|)\s*'([^']*)'")

#: Any quoted literal, used only when no result arm is found at all.
_ANY_LITERAL: typ.Final = re.compile(r"'([^']*)'")

#: The short-circuit idiom that stands in for a ternary. The condition is
#: matched greedily so a condition containing its own `&&` binds to the
#: last one, which is the operator that introduces the first arm.
_TERNARY: typ.Final = re.compile(
    r"^\s*\$\{\{\s*(?P<condition>.+)\s*&&\s*'(?P<when_true>[^']*)'"
    r"\s*\|\|\s*'(?P<when_false>[^']*)'\s*\}\}\s*$",
    re.DOTALL,
)

#: `ci.yml:build` is the only repository-owned build and test job. Every
#: other job is scheduled, API-bound, or release orchestration and must
#: stay on a GitHub-hosted runner.
BUILD_JOBS: typ.Final = frozenset({"ci.yml:build"})

#: The GitHub-hosted labels this repository uses. A label outside this
#: set is a paid runner and must be registered with actionlint.
GITHUB_HOSTED_LABELS: typ.Final = frozenset(
    {"ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04", "windows-latest", "macos-latest"}
)

GATE_WORKFLOW: typ.Final = "ci.yml"
TRUNK_REFERENCE: typ.Final = "refs/heads/main"

#: The short name of the branch `TRUNK_REFERENCE` names. Both spellings
#: are needed: a step's guard compares the full ref, a trigger's filter
#: lists the short name, and the reachability contract reads one against
#: the other.
TRUNK_BRANCH: typ.Final = "main"

#: The event field that distinguishes a fork's pull request. Named here
#: so the placement contract asserts this field rather than matching the
#: expression loosely: `head.repo.private` reads almost identically and
#: would send every private-repository pull request to a hosted runner.
FORK_FIELD: typ.Final = "github.event.pull_request.head.repo.fork"

#: The label a `runs-on` expression yields when neither reader below can
#: name a runner it selects. Returning an empty tuple instead left
#: `Job.declares_a_runner` false, and every placement contract skips a job
#: that declares no runner, so `runs-on: ${{ matrix.runner }}` passed them
#: all by being unreadable. A sentinel is in no registry and in no hosted
#: set, so the same contracts refuse it: the reader fails closed.
UNREADABLE_RUNNER: typ.Final = "<unreadable runs-on expression>"

__all__ = [
    "BUILD_JOBS",
    "FORK_FIELD",
    "GATE_WORKFLOW",
    "GITHUB_HOSTED_LABELS",
    "TRUNK_BRANCH",
    "TRUNK_REFERENCE",
    "UNREADABLE_RUNNER",
    "RunnerExpression",
    "build_job",
    "condition_names_field",
    "is_an_expression",
    "labels_in_expression",
    "read_runner_expression",
    "workflow_named",
]


def workflow_named(workflows: tuple[Workflow, ...], name: str) -> Workflow:
    """Return the workflow called ``name``.

    Parameters
    ----------
    workflows : tuple[Workflow, ...]
        Every loaded workflow.
    name : str
        The document's file name.

    Returns
    -------
    Workflow
        The matching workflow.

    Examples
    --------
    >>> workflow_named(load_workflows(), GATE_WORKFLOW).name  # doctest: +SKIP
    'ci.yml'
    """
    for workflow in workflows:
        if workflow.name == name:
            return workflow
    message = f"{name} is missing from the workflow directory"
    raise AssertionError(message)


def build_job(workflows: tuple[Workflow, ...]) -> Job:
    """Return the repository's single build and test job.

    Parameters
    ----------
    workflows : tuple[Workflow, ...]
        Every loaded workflow.

    Returns
    -------
    Job
        The job named by `BUILD_JOBS`.

    Examples
    --------
    >>> build_job(load_workflows()).identifier  # doctest: +SKIP
    'build'
    """
    for workflow in workflows:
        for job in workflow.jobs:
            if job.qualified_name in BUILD_JOBS:
                return job
    message = f"none of {sorted(BUILD_JOBS)} is declared"
    raise AssertionError(message)


@dc.dataclass(frozen=True)
class RunnerExpression:
    """A ``runs-on`` expression read as a condition and its two arms."""

    raw: str
    condition: str
    when_true: str
    when_false: str


def is_an_expression(raw: str) -> bool:
    """Report whether ``raw`` selects its runner by expression.

    Parameters
    ----------
    raw : str
        A job's ``runs-on`` value as the YAML parser produced it.

    Returns
    -------
    bool
        Whether the value interpolates rather than naming a label.

    Examples
    --------
    >>> is_an_expression("ubuntu-latest")
    False
    >>> is_an_expression("${{ inputs.runner }}")
    True
    """
    return "${{" in raw


def labels_in_expression(raw: str) -> tuple[str, ...]:
    """Return the labels an expression can select, in the order written.

    Only the operands of `&&` and `||` are labels. A quoted literal
    elsewhere belongs to the condition, and reading it as a runner is
    how a valid event-keyed declaration came to be reported as naming an
    unregistered runner.

    An expression with no result arm at all falls back to every quoted
    literal. That form selects no label this reader can name, and a
    placement contract that sees no labels asserts nothing at all, which
    is a worse failure than naming one the job cannot reach.

    When neither reader finds a literal, the expression names its runner
    somewhere this module cannot follow, such as `${{ matrix.runner }}`.
    `UNREADABLE_RUNNER` is returned rather than nothing, because nothing
    reads as "declares no runner" and every placement contract skips such
    a job. The sentinel belongs to no hosted set and to no registry, so
    the contracts refuse it and say which job needs a reader instead.

    Parameters
    ----------
    raw : str
        A job's ``runs-on`` value.

    Returns
    -------
    tuple[str, ...]
        The labels, in the order they appear, or `UNREADABLE_RUNNER`.

    Examples
    --------
    >>> labels_in_expression(
    ...     "${{ github.event_name == 'pull_request'"
    ...     " && 'ubuntu-latest' || 'ubicloud-standard-2' }}"
    ... )
    ('ubuntu-latest', 'ubicloud-standard-2')
    >>> labels_in_expression("${{ 'ubuntu-latest' }}")
    ('ubuntu-latest',)
    >>> labels_in_expression("${{ matrix.runner }}")
    ('<unreadable runs-on expression>',)
    """
    arms = tuple(_RESULT_ARM.findall(raw))
    return arms or tuple(_ANY_LITERAL.findall(raw)) or (UNREADABLE_RUNNER,)


def condition_names_field(condition: str, field: str) -> bool:
    """Report whether ``condition`` reads ``field`` and not a longer name.

    A placement condition may be compound, so the field cannot be
    asserted by equality: `fork && github.event_name == 'push'` names it
    and is not equal to it. A substring test admits the failure the
    assertion exists to catch, because `...head.repo.forked` contains
    `...head.repo.fork` and selects a field that does not exist, which
    evaluates false and sends every fork to the paid runner.

    The match is therefore bounded on both sides by anything that could
    continue an expression path: a word character or a dot.

    Parameters
    ----------
    condition : str
        A placement expression's condition.
    field : str
        The context field the condition must read.

    Returns
    -------
    bool
        Whether the condition reads exactly that field.

    Examples
    --------
    >>> condition_names_field(FORK_FIELD, FORK_FIELD)
    True
    >>> condition_names_field(f"{FORK_FIELD} && github.ref == 'x'", FORK_FIELD)
    True
    >>> condition_names_field(f"{FORK_FIELD}ed", FORK_FIELD)
    False
    >>> condition_names_field(f"{FORK_FIELD}.name", FORK_FIELD)
    False
    """
    bounded = rf"(?<![\w.]){re.escape(field)}(?![\w.])"
    return re.search(bounded, condition) is not None


def read_runner_expression(raw: str) -> RunnerExpression | None:
    """Return ``raw`` read as a condition and its two arms, or None.

    None means the value is not the short-circuit idiom: a bare label, an
    interpolation of a single value, or a shape this reader does not
    model. A contract that needs the arms says so by refusing None rather
    than by guessing which label was meant.

    Parameters
    ----------
    raw : str
        A job's ``runs-on`` value.

    Returns
    -------
    RunnerExpression or None
        The parsed expression, or None when ``raw`` is not one.

    Examples
    --------
    >>> read_runner_expression("ubuntu-latest") is None
    True
    >>> expression = read_runner_expression(
    ...     "${{ github.event_name == 'push'"
    ...     " && 'ubicloud-standard-8' || 'ubuntu-latest' }}"
    ... )
    >>> expression.condition
    "github.event_name == 'push'"
    >>> (expression.when_true, expression.when_false)
    ('ubicloud-standard-8', 'ubuntu-latest')
    """
    match = _TERNARY.match(raw)
    if match is None:
        return None
    return RunnerExpression(
        raw=raw,
        condition=match.group("condition").strip(),
        when_true=match.group("when_true"),
        when_false=match.group("when_false"),
    )
