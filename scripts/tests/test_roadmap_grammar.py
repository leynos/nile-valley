"""Contract: the ephemeral-previews roadmap keeps the grammar `mapsplice` reads.

`mapsplice` accepts phases written ``## N. Title`` and steps written
``### N.M. Title``, and rejects the ``## Phase N:`` and ``### N.M:`` forms this
document used before the change that aligned it. Nothing in the repository
stated that grammar, so the first tests here put the two readings side by side:
the headings this module calls canonical must be ones the tool accepts, and the
headings it calls legacy must be ones the tool rejects.

The remaining tests check the document itself. They read the text and assert
the phase and step numbering, without touching task text, status text, task
order, or checkbox states, so aligning a heading can never quietly reword a
task or tick a box.
"""

from __future__ import annotations

import re
import typing as typ

import pytest
import roadmap_grammar_support as grammar
import mapsplice_support as mapsplice

if typ.TYPE_CHECKING:
    from pathlib import Path

# The tool is not installed in CI, so only the checks that need it are
# skipped. Everything else reads the document with the patterns in
# `roadmap_grammar_support`, and runs wherever the suite runs -- otherwise the
# whole module would vanish from CI and validate nothing there. Skipping is
# deliberately not the module default: that is the shape that let a malformed
# committed file go unchecked.
needs_tool = pytest.mark.skipif(
    not mapsplice.available(),
    reason="mapsplice is not installed, so the tool cannot be re-checked here",
)

TEXT = grammar.read()

# The shapes the tool accepts, as standalone documents.
ACCEPTED = {
    "phase": "## 1. Application delivery and GitOps strategy\n",
    "phase-with-status": "## 1. Application delivery and GitOps strategy (To do)\n",
    "step": "## 1. A\n\n### 1.1. DigitalOcean Kubernetes cluster\n",
    "step-with-status": (
        "## 3. A\n\n### 3.1. Reusable idempotent actions (In progress)\n"
    ),
    "non-sequential": "## 1. A\n\n## 3. C\n\n### 3.2. D\n",
    "gapped-steps": "## 1. A\n\n### 1.1. B\n\n### 1.3. D\n",
}

# The shapes the tool rejects, and the form each one reintroduces.
REJECTED = {
    "legacy-phase-colon": "## Phase 1: Application delivery\n",
    "legacy-phase-dot": "## Phase 1. Application delivery\n",
    "legacy-step-colon": "## 1. A\n\n### 1.1: DigitalOcean Kubernetes cluster\n",
    "legacy-step-space": "## 1. A\n\n### 1.1 DigitalOcean Kubernetes cluster\n",
    "phase-without-dot": "## 1 Application delivery\n",
    "step-under-wrong-phase": "## 2. A\n\n### 1.1. B\n",
    "step-as-a-level-four-heading": "## 1. A\n\n#### 1.1. B\n",
}


@needs_tool
@pytest.mark.parametrize("name", sorted(ACCEPTED), ids=str)
def test_the_tool_accepts_the_canonical_forms(name: str) -> None:
    """Each accepted shape is one the tool itself accepts.

    Without this the patterns could be tightened into agreement with a grammar
    the tool does not have, and the document would fail `mapsplice` while these
    tests passed.
    """
    status, reason = mapsplice.rejects_text(ACCEPTED[name])

    assert status == 0, (
        f"the tool rejects the {name} form this contract calls canonical: {reason}"
    )


@needs_tool
@pytest.mark.parametrize("name", sorted(REJECTED), ids=str)
def test_the_tool_rejects_the_legacy_forms(name: str) -> None:
    """Each rejected shape is one the tool itself rejects.

    The document used all of these before it was aligned. A contract that
    accepted any of them would not have caught the regression that prompted
    this work.
    """
    status, reason = mapsplice.rejects_text(REJECTED[name])

    assert status != 0, (
        f"the tool accepts the {name} form, so the contract is too strict"
    )
    assert reason, f"the tool gave no reason for rejecting {name}"


@needs_tool
@pytest.mark.parametrize("name", sorted({**ACCEPTED, **REJECTED}), ids=str)
def test_the_reader_and_the_tool_agree(name: str) -> None:
    """The patterns and the tool give the same verdict on every sample.

    This is the check that keeps the two readings from drifting. The patterns
    are what the contract asserts in CI, and the tool is the authority they
    stand for, so a form one accepts and the other refuses is a defect in
    whichever is wrong -- and this is where it surfaces.
    """
    text = {**ACCEPTED, **REJECTED}[name]
    status, reason = mapsplice.rejects_text(text)
    found = grammar.problems(text)

    assert bool(found) == (status != 0), (
        f"the patterns and the tool disagree about the {name} form: "
        f"the tool exited {status} ({reason}) while the patterns found {found}"
    )


@needs_tool
def test_the_roadmap_itself_validates() -> None:
    """The document as committed is well formed, judged by the tool."""
    status, reason = mapsplice.validates()

    assert status == 0, f"mapsplice rejects the roadmap as committed: {reason}"


def test_the_body_starts_at_a_phase() -> None:
    """The phase-onward body is non-empty, so the tool has something to read.

    `mapsplice` will not accept a fragment that opens with prose. The tool is
    absent in CI, so the property it depends on is asserted here instead: the
    trim finds a phase and keeps the rest of the document.
    """
    body = grammar.fragment(TEXT)

    assert body, "no phase heading was found to start the body"
    assert body.startswith("## 1. "), f"the body starts at {body.splitlines()[0]!r}"
    assert body == body.rstrip() + "\n", "the body must keep its trailing newline"
    assert len(body.splitlines()) < len(TEXT.splitlines()), (
        "the trim must drop the front matter, not the whole document"
    )


def test_the_patterns_accept_the_canonical_forms() -> None:
    """Every shape the contract calls canonical reads as well formed here.

    Run wherever the suite runs, so the grammar is asserted in CI and not only
    on a machine that has the binary.
    """
    for name, text in ACCEPTED.items():
        found = grammar.problems(text)

        assert not found, (
            f"the patterns refuse the {name} form, which this contract calls "
            f"canonical: {found}"
        )


def test_the_patterns_reject_the_legacy_forms() -> None:
    """Every shape the tool refuses is refused by the patterns too.

    The tool check above is skipped wherever `mapsplice` is absent, so the
    rejection is proved against the patterns themselves as well. Without this
    the module would assert the canonical forms are accepted and never assert
    the legacy ones are refused, on every machine that lacks the binary.
    """
    for name, text in REJECTED.items():
        found = grammar.problems(text)

        assert found, f"the patterns accept the {name} form, which the tool rejects"


def test_no_heading_still_uses_a_legacy_form() -> None:
    """No phase or step heading remains in a form the tool rejects."""
    offenders = grammar.legacy_headings(TEXT)

    assert not offenders, (
        f"these headings reintroduce the pre-alignment forms: {offenders}"
    )


def test_every_heading_is_a_phase_or_a_step() -> None:
    """Nothing inside the roadmap body is a heading the grammar has no room for.

    `mapsplice` rejects a stray heading below the title, so this is the tool's
    rule read off the document rather than a separate opinion about how the
    roadmap should be written.
    """
    offenders = grammar.unrecognized_headings(TEXT)

    assert not offenders, f"the grammar admits no heading of this kind: {offenders}"


def test_the_reader_accepts_the_roadmap_as_committed() -> None:
    """The document satisfies the patterns, with no binary required.

    This is the CI-facing half of `test_the_roadmap_itself_validates`: the tool
    may be absent there, but the rules it enforces are still applied to the
    file as committed.
    """
    found = grammar.problems(TEXT)

    assert not found, f"the roadmap as committed is not well formed: {found}"


def test_the_phase_numbering_is_the_expected_sequence() -> None:
    """Phases are numbered 1 through 4, in order.

    The numbers are asserted rather than merely checked for uniqueness: a
    renumbering is a deliberate act that should have to update this test.
    """
    numbered = grammar.phases(TEXT)

    assert [phase.number for phase in numbered] == [1, 2, 3, 4], (
        f"unexpected phase numbering: {[(p.number, p.line) for p in numbered]}"
    )


def test_each_phase_carries_a_title() -> None:
    """A phase heading is a number, a dot, and a title."""
    empty = [
        f"line {phase.line}" for phase in grammar.phases(TEXT) if not phase.title
    ]

    assert empty == [], f"these phases have no title: {empty}"


def test_the_step_numbering_is_the_expected_sequence() -> None:
    """Steps run 2.1 to 2.4 and 3.1 to 3.3, in order.

    Phase 1 and phase 4 hold no steps, which is why the sequence is not
    continuous across the document.
    """
    numbered = grammar.steps(TEXT)

    assert [step.dotted for step in numbered] == [
        "2.1",
        "2.2",
        "2.3",
        "2.4",
        "3.1",
        "3.2",
        "3.3",
    ], f"unexpected step numbering: {[(s.dotted, s.line) for s in numbered]}"


def test_every_step_belongs_to_a_declared_phase() -> None:
    """A step's phase part names a phase that exists above it.

    This is the tool's own rule, and the one a careless renumber has broken
    before: `### 1.1.` under `## 2.` is rejected outright.
    """
    declared = {phase.number for phase in grammar.phases(TEXT)}
    orphans = [
        f"line {step.line}: {step.dotted}"
        for step in grammar.steps(TEXT)
        if step.phase not in declared
    ]

    assert orphans == [], (
        f"these steps name a phase the document does not declare: {orphans}"
    )


def test_each_step_follows_its_own_phase() -> None:
    """Steps appear under the phase they number, not under another one.

    A heading may be internally well formed and still sit in the wrong place;
    the tool checks the number, not the position, so the position is checked
    here.
    """
    current = None
    misplaced = []
    for number, line in grammar.body_lines(TEXT):
        phase = grammar.PHASE.match(line)
        if phase is not None:
            current = int(phase.group("number"))
            continue
        step = grammar.STEP.match(line)
        if step is not None and int(step.group("phase")) != current:
            misplaced.append(
                f"line {number}: step {step.group('phase')}.{step.group('step')} "
                f"sits under phase {current}"
            )

    assert misplaced == [], f"these steps sit under the wrong phase: {misplaced}"


def test_the_task_content_is_untouched_by_the_alignment() -> None:
    """The alignment changed headings, not tasks.

    The headings are the only lines this contract governs, so removing them
    must leave the task list exactly as it is. This is the check that fails if
    a renumbering edit also rewords a task, reorders one, or ticks a box.
    """
    stripped = [
        line
        for line in TEXT.splitlines()
        if not grammar.PHASE.match(line) and not grammar.STEP.match(line)
    ]

    assert len(stripped) == len(TEXT.splitlines()) - 11, (
        "the document holds 4 phases and 7 steps, so 11 headings are expected"
    )
    assert any(line.startswith("- [ ]") for line in stripped), (
        "the task list must still hold unchecked items"
    )
    assert any(line.startswith("- [x]") for line in stripped), (
        "the task list must still hold checked items"
    )
    assert re.search(r"^\- \[[ x]\] \*\*.+\*\*", "\n".join(stripped), re.MULTILINE), (
        "task items must keep their bold lead-in"
    )


def test_the_checked_and_unchecked_counts_are_preserved() -> None:
    """Checkbox states are counted, so an edit that ticks a box is visible.

    The counts come from the document as it stands. A task marked done as part
    of real work should update these numbers, which is the point: the change
    becomes deliberate rather than incidental to a heading edit.
    """
    lines = TEXT.splitlines()
    checked = sum(1 for line in lines if re.match(r"^\s*- \[x\]", line))
    unchecked = sum(1 for line in lines if re.match(r"^\s*- \[ \]", line))

    assert (checked, unchecked) == (18, 38), (
        f"checkbox counts changed: {checked} checked, {unchecked} unchecked"
    )


def test_status_suffixes_are_read_as_part_of_the_title() -> None:
    """A phase's status suffix survives in the title this contract reads."""
    titles = {phase.number: phase.title for phase in grammar.phases(TEXT)}

    assert titles[1].endswith("(To do)"), f"phase 1 title is {titles[1]!r}"
    assert titles[3].endswith("(In progress)"), f"phase 3 title is {titles[3]!r}"
    assert titles[4].endswith("(Not started)"), f"phase 4 title is {titles[4]!r}"
