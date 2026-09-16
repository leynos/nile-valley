"""Structural contracts for the repository's GitHub Actions workflows.

These tests encode the Ubicloud adoption rules that a reviewer cannot check
reliably by eye: no tool may be built from source, every mutable cache path
must have exactly one owner, cache writes belong to trunk, non-build jobs stay
GitHub-hosted, and every installer runs before the gate that uses it.
"""

from __future__ import annotations

import re
import typing as typ

import pytest
from workflow_contract_support import (
    Job,
    Step,
    Workflow,
    cache_paths,
    iter_jobs,
    iter_steps,
    load_workflows,
    registered_self_hosted_labels,
)

if typ.TYPE_CHECKING:
    from collections.abc import Iterator

# `ci.yml:build` is the only repository-owned build and test job. Every other
# job is scheduled, API-bound, or release orchestration and must stay on a
# GitHub-hosted runner.
BUILD_JOBS = frozenset({"ci.yml:build"})
GITHUB_HOSTED_LABELS = frozenset(
    {"ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04", "windows-latest", "macos-latest"}
)

CACHE_ACTION_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
SHARED_ACTIONS_SHA = "c5a54701c8603a0fa756a6b34c49bc2af75a6c11"
TRUNK_REFERENCE = "refs/heads/main"
#: The short name of the branch `TRUNK_REFERENCE` names. Both spellings
#: are needed: a step's guard compares the full ref, a trigger's filter
#: lists the short name, and the reachability contract reads one against
#: the other.
TRUNK_BRANCH = "main"
GATE_WORKFLOW = "ci.yml"
#: The event field that distinguishes a fork's pull request. Named here
#: so the placement contract asserts this field rather than matching the
#: expression loosely: `head.repo.private` reads almost identically and
#: would send every private-repository pull request to a hosted runner.
FORK_FIELD = "github.event.pull_request.head.repo.fork"

# Forms that compile a tool from source inside CI. `uv tool install` is absent
# from this list because uv resolves published wheels rather than building the
# tool's own sources.
SOURCE_BUILD_PATTERNS = (
    re.compile(r"\bcargo\s+install\b"),
    re.compile(r"\bgo\s+install\b"),
    re.compile(r"\bgo\s+get\b"),
    re.compile(r"\bmake\s+install\b"),
    re.compile(r"\bpip\s+install\b.*--no-binary"),
)

# Steps that must all precede the first `make` gate.
INSTALLER_STEP_IDS = (
    "expose-local-bin",
    "tooling-cache",
    "workspace-uv-cache",
    "bun-cache",
    "puppeteer-cache",
    "tflint-cache",
    "setup-bun",
    "setup-uv",
    "install-nixie",
    "setup-helm",
    "install-uv-tools",
    "install-action-validator",
    "install-actionlint",
    "install-checkmake",
    "install-tflint",
    "install-dependencies",
    "expose-node-modules-bin",
)

# Installers that download a release artefact and must skip the download when
# the tooling cache already holds a matching, verified executable.
PROBE_GUARDED_INSTALLERS = {
    "install-uv-tools": ("yamllint --version", "mbake --version"),
    "install-action-validator": ("action-validator --version",),
    "install-actionlint": ("actionlint -version",),
    "install-checkmake": ("checkmake --version",),
}

# The verification targets. `make deps` is an installer, not a gate, so it is
# deliberately absent: it belongs before the first gate rather than being one.
# `markdownlint` is deliberately absent: Markdown linting runs through the
# pinned markdownlint-cli2 action, as the estate's markdown-formatting-baseline
# rule requires, not through a Make invocation.
GATE_TARGETS = (
    "spelling",
    "nixie",
    "yamllint",
    "lint",
    "check-fmt",
    "test",
)

# Installers that fetch an archive over the network must verify a pinned digest.
CHECKSUM_VERIFIED_INSTALLERS = ("install-actionlint", "install-checkmake")


@pytest.fixture(name="workflows", scope="module")
def workflows_fixture() -> tuple[Workflow, ...]:
    """Parse every workflow document once for the whole module."""
    return load_workflows()


def _build_job(workflows: tuple[Workflow, ...]) -> Job:
    for job in iter_jobs(workflows):
        if job.qualified_name in BUILD_JOBS:
            return job
    pytest.fail("the ci.yml build job is missing")


def _workflow_named(workflows: tuple[Workflow, ...], name: str) -> Workflow:
    for workflow in workflows:
        if workflow.name == name:
            return workflow
    pytest.fail(f"no workflow named {name!r}")


def _step_by_id(job: Job, identifier: str) -> Step:
    for step in job.steps:
        if step.identifier == identifier:
            return step
    pytest.fail(f"{job.qualified_name} has no step with id {identifier!r}")


def _run_scripts(workflows: tuple[Workflow, ...]) -> Iterator[tuple[str, str]]:
    for job, step in iter_steps(workflows):
        if step.run:
            yield f"{job.qualified_name}/{step.name}", step.run


@pytest.mark.parametrize("pattern", SOURCE_BUILD_PATTERNS, ids=lambda p: p.pattern)
def test_no_job_builds_a_tool_from_source(
    workflows: tuple[Workflow, ...], pattern: re.Pattern[str]
) -> None:
    """CI installs prebuilt binaries; a source build is a policy failure."""
    offenders = [
        location for location, script in _run_scripts(workflows) if pattern.search(script)
    ]
    assert not offenders, (
        f"source-build form {pattern.pattern!r} found in: {offenders}. "
        "Replace it with a pinned, checksum-verified release artefact."
    )


def test_prebuilt_installers_fail_closed(workflows: tuple[Workflow, ...]) -> None:
    """Installer actions must not silently fall back to compiling a tool."""
    for job, step in iter_steps(workflows):
        if step.uses.startswith("taiki-e/install-action"):
            assert step.inputs.get("fallback") == "none", (
                f"{job.qualified_name}/{step.name} must set fallback: none"
            )
        if "cargo-binstall" in step.run:
            assert "--strategies crate-meta-data,quick-install" in step.run, (
                f"{job.qualified_name}/{step.name} must restrict binstall strategies"
            )


def test_cache_actions_are_pinned(workflows: tuple[Workflow, ...]) -> None:
    """Every cache step uses the reviewed actions/cache v6.1.0 commit."""
    for job, step in iter_steps(workflows):
        assert not step.uses.startswith("ubicloud/cache"), (
            f"{job.qualified_name}/{step.name} uses the deprecated ubicloud/cache fork"
        )
        if step.is_cache_step:
            assert step.uses.endswith(f"@{CACHE_ACTION_SHA}"), (
                f"{job.qualified_name}/{step.name} must pin actions/cache to "
                f"{CACHE_ACTION_SHA}"
            )


def test_each_cache_path_has_one_owner(workflows: tuple[Workflow, ...]) -> None:
    """A mutable cache path belongs to exactly one key, hence one owner."""
    owners: dict[str, set[str]] = {}
    for _job, step in iter_steps(workflows):
        if not step.is_cache_step:
            continue
        key = str(step.inputs.get("key", ""))
        for path in cache_paths(step):
            owners.setdefault(path, set()).add(key)
    shared = {path: keys for path, keys in owners.items() if len(keys) > 1}
    assert not shared, f"cache paths with more than one owner: {sorted(shared)}"


def test_setup_uv_does_not_own_the_uv_download_cache(
    workflows: tuple[Workflow, ...],
) -> None:
    """The tooling cache owns ``~/.cache/uv``; setup-uv must not duplicate it."""
    step = _step_by_id(_build_job(workflows), "setup-uv")
    assert step.inputs.get("enable-cache") is False, (
        "astral-sh/setup-uv must set enable-cache: false so the tooling cache "
        "remains the single owner of ~/.cache/uv"
    )


def test_cache_writes_are_restricted_to_trunk(workflows: tuple[Workflow, ...]) -> None:
    """Pull requests restore the trusted generation but never publish one."""
    save_steps = [
        (job, step) for job, step in iter_steps(workflows) if step.is_cache_save
    ]
    assert save_steps, "the build job must save at least one cache on trunk"
    for job, step in save_steps:
        assert TRUNK_REFERENCE in step.condition, (
            f"{job.qualified_name}/{step.name} must guard its save with "
            f"{TRUNK_REFERENCE}"
        )


def test_every_restored_cache_has_a_matching_save(
    workflows: tuple[Workflow, ...],
) -> None:
    """A restore without a writer can never warm; keys must be paired."""
    restored = {
        str(step.inputs.get("key", ""))
        for _job, step in iter_steps(workflows)
        if step.is_cache_step and not step.is_cache_save
    }
    saved = {
        str(step.inputs.get("key", ""))
        for _job, step in iter_steps(workflows)
        if step.is_cache_save
    }
    assert restored == saved, (
        f"restore keys without a save: {sorted(restored - saved)}; "
        f"save keys without a restore: {sorted(saved - restored)}"
    )


def test_non_build_jobs_stay_github_hosted(workflows: tuple[Workflow, ...]) -> None:
    """Scheduled, metadata, and orchestration jobs keep GitHub-hosted runners."""
    for job in iter_jobs(workflows):
        if job.qualified_name in BUILD_JOBS or not job.declares_a_runner:
            continue
        stray = [
            label for label in job.runner_labels if label not in GITHUB_HOSTED_LABELS
        ]
        assert not stray, (
            f"{job.qualified_name} is not a build job and must run on "
            f"GitHub-hosted labels only, not {stray!r}"
        )


def test_build_job_declares_a_timeout(workflows: tuple[Workflow, ...]) -> None:
    """A self-hosted job without a timeout can burn the budget on a hang."""
    job = _build_job(workflows)
    assert job.timeout_minutes is not None, f"{job.qualified_name} needs timeout-minutes"


def test_self_hosted_labels_are_registered_with_actionlint(
    workflows: tuple[Workflow, ...],
) -> None:
    """Every intentional non-GitHub label is declared for actionlint."""
    registered = registered_self_hosted_labels()
    used = {
        label
        for job in iter_jobs(workflows)
        for label in job.runner_labels
        if label not in GITHUB_HOSTED_LABELS
    }
    assert used <= registered, (
        f"labels missing from .github/actionlint.yaml: {sorted(used - registered)}"
    )
    assert registered <= used, (
        f"labels registered but unused: {sorted(registered - used)}"
    )


def test_shared_action_references_are_pinned(workflows: tuple[Workflow, ...]) -> None:
    """Shared-actions callers pin the reviewed commit, never a branch."""
    references = [
        (f"{job.qualified_name}/{step.name}", step.uses)
        for job, step in iter_steps(workflows)
        if step.uses.startswith("leynos/shared-actions")
    ]
    references += [
        (job.qualified_name, job.uses)
        for job in iter_jobs(workflows)
        if job.uses.startswith("leynos/shared-actions")
    ]
    assert references, "expected at least one leynos/shared-actions reference"
    for location, reference in references:
        assert reference.endswith(f"@{SHARED_ACTIONS_SHA}"), (
            f"{location} must pin leynos/shared-actions to {SHARED_ACTIONS_SHA}"
        )


def test_every_third_party_action_is_pinned_to_a_commit(
    workflows: tuple[Workflow, ...],
) -> None:
    """A floating tag lets an upstream force-push change what CI executes."""
    commit_reference = re.compile(r"@[0-9a-f]{40}$")
    references = [
        (f"{job.qualified_name}/{step.name}", step.uses)
        for job, step in iter_steps(workflows)
        if step.uses
    ]
    # A reusable workflow is called at job level, so it escapes a step-only loop.
    references += [
        (job.qualified_name, job.uses) for job in iter_jobs(workflows) if job.uses
    ]
    for location, reference in references:
        if reference.startswith("./"):
            continue
        assert commit_reference.search(reference), (
            f"{location} must pin {reference!r} to a commit"
        )


def test_installers_precede_the_first_gate(workflows: tuple[Workflow, ...]) -> None:
    """Every tool is installed before the first `make` target that needs it."""
    job = _build_job(workflows)
    gate_pattern = re.compile(rf"^\s*make\s+({'|'.join(GATE_TARGETS)})\s*$")
    gate_indices = [
        step.index for step in job.steps if gate_pattern.match(step.run.strip())
    ]
    assert len(gate_indices) == len(GATE_TARGETS), (
        f"expected one step per gate target {GATE_TARGETS}, found {len(gate_indices)}"
    )
    first_gate = min(gate_indices)
    late = [
        step.identifier
        for step in job.steps
        if step.identifier in INSTALLER_STEP_IDS and step.index > first_gate
    ]
    assert not late, f"installer steps run after the first gate: {late}"


def test_declared_installer_steps_all_exist(workflows: tuple[Workflow, ...]) -> None:
    """The ordering contract is meaningless if it names absent steps."""
    job = _build_job(workflows)
    present = {step.identifier for step in job.steps}
    missing = [identifier for identifier in INSTALLER_STEP_IDS if identifier not in present]
    assert not missing, f"installer steps named by the contract are missing: {missing}"


@pytest.mark.parametrize(
    ("identifier", "probes"), sorted(PROBE_GUARDED_INSTALLERS.items())
)
def test_installers_probe_the_warm_cache(
    workflows: tuple[Workflow, ...], identifier: str, probes: tuple[str, ...]
) -> None:
    """A warm tooling cache must skip the download it already satisfies."""
    step = _step_by_id(_build_job(workflows), identifier)
    for probe in probes:
        assert probe in step.run, f"{identifier} must probe with {probe!r}"


@pytest.mark.parametrize("identifier", CHECKSUM_VERIFIED_INSTALLERS)
def test_downloaded_archives_are_checksum_verified(
    workflows: tuple[Workflow, ...], identifier: str
) -> None:
    """A pinned URL without a digest check is not a trusted binary source."""
    step = _step_by_id(_build_job(workflows), identifier)
    assert "sha256sum --check --strict" in step.run, (
        f"{identifier} must verify the downloaded artefact against a pinned digest"
    )


def test_the_gate_runs_on_trunk_as_well_as_on_a_pull_request(
    workflows: tuple[Workflow, ...],
) -> None:
    """The gate fires on a push to trunk, not only before one.

    Without it a merge that breaks the gate is invisible until somebody
    opens the next pull request, and the trunk-guarded cache saves below
    have no event that can reach them.

    Mutation: deleting the `push` trigger from `ci.yml` failed this.
    """
    gate = _workflow_named(workflows, GATE_WORKFLOW)
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

    Mutation: replacing `head.repo.fork` with `head.repo.private` failed
    this; so did removing the expression for a bare label.
    """
    job = _build_job(workflows)
    declaration = job.raw_runs_on

    assert job.selects_its_runner_by_expression, (
        f"{job.qualified_name} selects a runner unconditionally, so a fork's "
        f"pull request cannot run it: {declaration!r}"
    )
    assert FORK_FIELD in declaration, (
        f"{job.qualified_name} must key its fallback on {FORK_FIELD}: "
        f"{declaration!r}"
    )
    hosted = [
        label for label in job.runner_labels if label in GITHUB_HOSTED_LABELS
    ]
    ubicloud = [
        label for label in job.runner_labels if label not in GITHUB_HOSTED_LABELS
    ]
    assert hosted and ubicloud, (
        f"{job.qualified_name} must name one hosted arm and one Ubicloud arm: "
        f"{job.runner_labels!r}"
    )
