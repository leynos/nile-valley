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
REQUIRED_GATES = (
    "make spelling",
    "make markdownlint",
    "make nixie",
    "make yamllint",
    "make lint",
    "make check-fmt",
    "make test",
)

MUTATED_GATE = "make lint"


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


def _condition_on_step(condition: object) -> typ.Callable[[Document], None]:
    """Return a mutation that puts ``condition`` on the gate's step."""

    def mutate(document: Document) -> None:
        find_step(document, MUTATED_GATE)["if"] = condition

    return mutate


def _condition_on_job(condition: object) -> typ.Callable[[Document], None]:
    """Return a mutation that puts ``condition`` on the gate's job."""

    def mutate(document: Document) -> None:
        find_job(document, MUTATED_GATE)["if"] = condition

    return mutate


def _replace_run(replacement: str) -> typ.Callable[[Document], None]:
    """Return a mutation that rewrites the gate step's run value."""

    def mutate(document: Document) -> None:
        find_step(document, MUTATED_GATE)["run"] = replacement

    return mutate


def _drop_pull_request_trigger(document: Document) -> None:
    """Remove the pull_request event from the workflow's triggers."""
    for key in ("on", True):
        raw = document.get(key)
        if isinstance(raw, dict) and "pull_request" in raw:
            del raw["pull_request"]


MUTATIONS = {
    # `if: false` parses to a boolean, so a check reading the value as text
    # sees an empty string and reports no condition.
    "step-if-false": _condition_on_step(False),
    "step-if-false-string": _condition_on_step("false"),
    "job-if-false": _condition_on_job(False),
    # A plausible condition is not falsy at all, and skips every pull request.
    "step-push-only": _condition_on_step("github.event_name == 'push'"),
    "job-push-only": _condition_on_job("github.ref == 'refs/heads/main'"),
    # The command survives, but nothing runs it.
    "wrapped": _replace_run(f"if false; then {MUTATED_GATE}; fi"),
    "ignored-failure": _replace_run(f"{MUTATED_GATE} || true"),
    "changed-command": _replace_run("make lin"),
    "trigger-removed": _drop_pull_request_trigger,
}


@pytest.mark.parametrize("name", sorted(MUTATIONS), ids=str)
def test_the_contract_rejects_each_mutation(name: str, document: Document) -> None:
    """Every way of neutralizing the gate is reported.

    Without this the contract could quietly stop checking anything and still
    pass, which is the failure it exists to prevent.
    """
    mutated = with_mutation(document, MUTATIONS[name])

    assert gate_failures(mutated, MUTATED_GATE) != [], (
        f"the {name} mutation left the gate looking healthy"
    )


def test_a_conditioned_duplicate_does_not_disqualify_the_gate(
    document: Document,
) -> None:
    """One unconditional step is enough, whatever a duplicate carries.

    A workflow may run the same gate twice, for instance on a second platform
    behind a condition. The contract asks that the gate runs unconditionally
    somewhere, not that no conditioned copy exists.
    """

    def add_conditioned_duplicate(mutated: Document) -> None:
        job = find_job(mutated, MUTATED_GATE)
        duplicate = {"name": "Lint again", "run": MUTATED_GATE, "if": False}
        job["steps"].insert(0, duplicate)

    mutated = with_mutation(document, add_conditioned_duplicate)

    assert gate_failures(mutated, MUTATED_GATE) == [], (
        "the unconditional step still satisfies the contract"
    )


def test_an_unmutated_document_still_passes(document: Document) -> None:
    """The mutations are what fail, not the copying the harness does."""
    unchanged = with_mutation(document, lambda _: None)

    assert gate_failures(unchanged, MUTATED_GATE) == [], (
        "the harness must not disturb the document it copies"
    )
