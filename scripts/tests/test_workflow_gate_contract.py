"""Contract: CI runs every Make gate, unconditionally, on a pull request.

Converting the recipes only helps if the workflow still runs them. A contract
that searched a step's ``run`` for the command would pass on a step that never
executes, so this one requires the whole shape: the job exists, some step's
entire ``run`` is the gate command, and neither the job nor that step carries
a condition.

Each mutation below is a way that shape can be broken while the command stays
in the file.
"""

from __future__ import annotations

import typing as typ

import pytest
from workflow_gate_support import (
    find_job,
    find_step,
    gate_failures,
    load_document,
    triggers,
    with_mutation,
)

if typ.TYPE_CHECKING:
    from workflow_gate_support import Document

# The gates the workflow must run. `make deps` is setup, not a gate.
# `make markdownlint` is deliberately absent: Markdown linting runs through
# the pinned markdownlint-cli2 action, as the estate's
# markdown-formatting-baseline rule requires, not through a Make invocation.
REQUIRED_GATES = (
    "make spelling",
    "make nixie",
    "make yamllint",
    "make lint",
    "make typecheck",
    "make check-fmt",
    "make test",
)

# The gates put through the mutation harness. Proof that the contract bites is
# only meaningful per gate, because each one is found by its own step, and the
# newest of them (`typecheck`) is the one a later edit is most likely to drop.
MUTATED_GATES = ("make lint", "make typecheck")


@pytest.fixture(name="document")
def document_fixture() -> Document:
    """Parse the continuous integration workflow once per test."""
    return load_document()


@pytest.mark.parametrize("command", REQUIRED_GATES, ids=str)
def test_ci_runs_the_gate(command: str, document: Document) -> None:
    """The workflow runs the gate with no condition on the step or the job."""
    failures = gate_failures(document, command)

    assert failures == [], f"{command} is not run unconditionally: {failures}"


def test_the_workflow_reacts_to_pull_requests(document: Document) -> None:
    """The gates would never run on a pull request without the trigger."""
    assert "pull_request" in triggers(document), (
        f"the workflow reacts only to {sorted(triggers(document))}"
    )


def _condition_on_step(
    gate: str, condition: object
) -> typ.Callable[[Document], None]:
    """Return a mutation that puts ``condition`` on the gate's step."""

    def mutate(document: Document) -> None:
        find_step(document, gate)["if"] = condition

    return mutate


def _condition_on_job(gate: str, condition: object) -> typ.Callable[[Document], None]:
    """Return a mutation that puts ``condition`` on the gate's job."""

    def mutate(document: Document) -> None:
        find_job(document, gate)["if"] = condition

    return mutate


def _replace_run(gate: str, replacement: str) -> typ.Callable[[Document], None]:
    """Return a mutation that rewrites the gate step's run value."""

    def mutate(document: Document) -> None:
        find_step(document, gate)["run"] = replacement

    return mutate


def _drop_step(gate: str) -> typ.Callable[[Document], None]:
    """Return a mutation that removes the gate's step from the workflow.

    This is the plainest way to stop a gate running, and the one an edit is
    most likely to do by accident, so the contract has to name it even though
    the command leaves the file entirely.
    """

    def mutate(document: Document) -> None:
        job = find_job(document, gate)
        job["steps"].remove(find_step(document, gate))

    return mutate


def _drop_pull_request_trigger(document: Document) -> None:
    """Remove the pull_request event from the workflow's triggers."""
    for key in ("on", True):
        raw = document.get(key)
        if isinstance(raw, dict) and "pull_request" in raw:
            del raw["pull_request"]


def _shorten(command: str) -> str:
    """Return a misspelling of ``command`` that still parses as YAML."""
    return command[:-1]


def _mutations(gate: str) -> dict[str, typ.Callable[[Document], None]]:
    """Return every way ``gate`` can be neutralized, keyed by name."""
    return {
        # `if: false` parses to a boolean, so a check reading the value as text
        # sees an empty string and reports no condition.
        "step-if-false": _condition_on_step(gate, False),
        "step-if-false-string": _condition_on_step(gate, "false"),
        "job-if-false": _condition_on_job(gate, False),
        # A plausible condition is not falsy at all, and skips every pull
        # request.
        "step-push-only": _condition_on_step(gate, "github.event_name == 'push'"),
        "job-push-only": _condition_on_job(gate, "github.ref == 'refs/heads/main'"),
        # The command survives, but nothing runs it.
        "wrapped": _replace_run(gate, f"if false; then {gate}; fi"),
        "ignored-failure": _replace_run(gate, f"{gate} || true"),
        "changed-command": _replace_run(gate, _shorten(gate)),
        "step-removed": _drop_step(gate),
        "trigger-removed": _drop_pull_request_trigger,
    }


@pytest.mark.parametrize("gate", MUTATED_GATES, ids=str)
@pytest.mark.parametrize("name", sorted(_mutations(MUTATED_GATES[0])), ids=str)
def test_the_contract_rejects_each_mutation(
    name: str, gate: str, document: Document
) -> None:
    """Every way of neutralizing the gate is reported.

    Without this the contract could quietly stop checking anything and still
    pass, which is the failure it exists to prevent.
    """
    mutated = with_mutation(document, _mutations(gate)[name])

    assert gate_failures(mutated, gate) != [], (
        f"the {name} mutation left {gate} looking healthy"
    )


@pytest.mark.parametrize("gate", MUTATED_GATES, ids=str)
def test_a_conditioned_duplicate_does_not_disqualify_the_gate(
    gate: str, document: Document
) -> None:
    """One unconditional step is enough, whatever a duplicate carries.

    A workflow may run the same gate twice, for instance on a second platform
    behind a condition. The contract asks that the gate runs unconditionally
    somewhere, not that no conditioned copy exists.
    """

    def add_conditioned_duplicate(mutated: Document) -> None:
        job = find_job(mutated, gate)
        duplicate = {"name": "Again", "run": gate, "if": False}
        job["steps"].insert(0, duplicate)

    mutated = with_mutation(document, add_conditioned_duplicate)

    assert gate_failures(mutated, gate) == [], (
        "the unconditional step still satisfies the contract"
    )


@pytest.mark.parametrize("gate", MUTATED_GATES, ids=str)
def test_an_unmutated_document_still_passes(gate: str, document: Document) -> None:
    """The mutations are what fail, not the copying the harness does."""
    unchanged = with_mutation(document, lambda _: None)

    assert gate_failures(unchanged, gate) == [], (
        "the harness must not disturb the document it copies"
    )
