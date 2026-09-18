"""Helpers for reading GitHub Actions workflows in contract tests.

The workflow contracts assert structural properties of every workflow in
``.github/workflows``. These helpers turn the raw YAML into small, typed
records so each contract test can state one property without re-parsing the
documents.

Two readers live beside this one rather than in it, because no code file
here may exceed 400 lines: :mod:`scripts.tests.workflow_filter_support`
reads a branch filter, and :mod:`scripts.tests.workflow_placement_support`
reads a `runs-on` expression.

Examples
--------
>>> workflows = load_workflows()  # doctest: +SKIP
>>> sorted(workflow.name for workflow in workflows)  # doctest: +SKIP
['ci.yml', 'delayed-pr-comment.yml', 'dependabot-automerge.yml']
"""

from __future__ import annotations

import dataclasses as dc
import re
import typing as typ
from pathlib import Path

import yaml
from workflow_filter_support import branch_filter_admits
from workflow_placement_support import is_an_expression, labels_in_expression

if typ.TYPE_CHECKING:
    from collections.abc import Iterator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
ACTIONLINT_CONFIG = REPOSITORY_ROOT / ".github" / "actionlint.yaml"

__all__ = [
    "ACTIONLINT_CONFIG",
    "REPOSITORY_ROOT",
    "WORKFLOW_DIRECTORY",
    "Job",
    "Step",
    "Workflow",
    "cache_paths",
    "iter_jobs",
    "iter_steps",
    "load_workflows",
    "runner_labels",
    "registered_self_hosted_labels",
]


@dc.dataclass(frozen=True)
class Step:
    """One step of a workflow job."""

    index: int
    name: str
    identifier: str
    uses: str
    run: str
    condition: str
    inputs: dict[str, object]

    @property
    def is_cache_step(self) -> bool:
        """Report whether the step calls any variant of ``actions/cache``."""
        return self.uses.startswith("actions/cache")

    @property
    def is_cache_save(self) -> bool:
        """Report whether the step saves rather than restores a cache."""
        return self.uses.startswith("actions/cache/save")


@dc.dataclass(frozen=True)
class Job:
    """One job of a workflow, with the fields the contracts inspect."""

    workflow: str
    identifier: str
    runner_labels: tuple[str, ...]
    raw_runs_on: str
    uses: str
    timeout_minutes: int | None
    steps: tuple[Step, ...]

    @property
    def qualified_name(self) -> str:
        """Return a stable ``workflow.yml:job`` label for assertion messages."""
        return f"{self.workflow}:{self.identifier}"

    @property
    def declares_a_runner(self) -> bool:
        """Report whether the job selects its own runner rather than a callee's."""
        return bool(self.runner_labels)

    @property
    def selects_its_runner_by_expression(self) -> bool:
        """Report whether ``runs-on`` is an expression rather than a label."""
        return is_an_expression(self.raw_runs_on)


@dc.dataclass(frozen=True)
class Workflow:
    """A parsed workflow document."""

    name: str
    path: Path
    triggers: dict[str, object]
    jobs: tuple[Job, ...]

    def writes_trunk_automatically(self, trunk_branch: str) -> bool:
        """Report whether an automatic event can run this on ``trunk_branch``.

        A manual `workflow_dispatch` can be aimed at any branch, so it
        satisfies a trunk guard in principle and warms nothing in
        practice: a cache that is written only when somebody remembers to
        press a button is a cache that is never written. Only the events
        that fire by themselves count here, which is a push whose branch
        filter admits trunk, and a schedule, which runs on the default
        branch.

        Parameters
        ----------
        trunk_branch : str
            The default branch's short name.

        Returns
        -------
        bool
            Whether some declared trigger produces the trunk ref unaided.
        """
        if "schedule" in self.triggers:
            return True
        if "push" not in self.triggers:
            return False
        push = self.triggers["push"]
        if not isinstance(push, dict):
            # A valueless `push:` filters nothing, so every branch fires.
            return True
        return branch_filter_admits(push, trunk_branch)


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _text_items(raw: list[object]) -> tuple[str, ...]:
    """Return the string members of ``raw``, discarding the rest."""
    return tuple(item for item in raw if isinstance(item, str))


def _labels_from_scalar(raw: str) -> tuple[str, ...]:
    """Return the labels a scalar ``runs-on`` can select.

    An expression yields its quoted arms; anything else is one label.
    """
    if is_an_expression(raw):
        return labels_in_expression(raw)
    return (raw,)


def _labels_from_group(raw: dict[str, object]) -> tuple[str, ...]:
    """Return the labels a ``group``/``labels`` mapping selects."""
    labels = raw.get("labels")
    if isinstance(labels, str):
        return _labels_from_scalar(labels)
    if isinstance(labels, list):
        return _text_items(labels)
    return ()


def runner_labels(raw: object) -> tuple[str, ...]:
    """Normalize every ``runs-on`` form into a tuple of selectable labels.

    GitHub Actions accepts a scalar label, a sequence of labels, and a mapping
    with ``group`` and ``labels`` keys. Treating the non-scalar forms as absent
    would let a self-hosted job slip past the placement contracts.

    An expression is normalized to the arms it can select. A job whose
    placement is keyed on the event still lands on one of a closed set of
    runners, and that set is what every placement contract is about; taking
    the expression itself as a label would report one unregistered runner
    that does not exist and miss both of the ones that do.
    """
    if isinstance(raw, str):
        return _labels_from_scalar(raw)
    if isinstance(raw, list):
        return _text_items(raw)
    if isinstance(raw, dict):
        return _labels_from_group(raw)
    return ()


def _step_from_mapping(index: int, raw: dict[str, object]) -> Step:
    inputs = raw.get("with")
    return Step(
        index=index,
        name=_as_text(raw.get("name")) or _as_text(raw.get("uses")),
        identifier=_as_text(raw.get("id")),
        uses=_as_text(raw.get("uses")),
        run=_as_text(raw.get("run")),
        condition=_as_text(raw.get("if")),
        inputs=inputs if isinstance(inputs, dict) else {},
    )


def _job_from_mapping(workflow: str, identifier: str, raw: dict[str, object]) -> Job:
    raw_steps = raw.get("steps")
    steps = tuple(
        _step_from_mapping(index, step)
        for index, step in enumerate(raw_steps if isinstance(raw_steps, list) else [])
        if isinstance(step, dict)
    )
    timeout = raw.get("timeout-minutes")
    runs_on = raw.get("runs-on")
    return Job(
        workflow=workflow,
        identifier=identifier,
        runner_labels=runner_labels(runs_on),
        raw_runs_on=_as_text(runs_on),
        uses=_as_text(raw.get("uses")),
        timeout_minutes=timeout if isinstance(timeout, int) else None,
        steps=steps,
    )


def _triggers(document: object) -> dict[str, object]:
    """Return the workflow's ``on`` mapping, however it was spelled.

    ``on`` is YAML 1.1's boolean true, so a document that leaves the key
    unquoted parses it as ``True`` and a lookup by the string misses. Both
    spellings are in this repository.
    """
    if not isinstance(document, dict):
        return {}
    raw = document.get("on", document.get(True))
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return dict.fromkeys(event for event in raw if isinstance(event, str))
    if isinstance(raw, str):
        return {raw: None}
    return {}


def _workflow_from_path(path: Path) -> Workflow:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_jobs = document.get("jobs", {}) if isinstance(document, dict) else {}
    jobs = tuple(
        _job_from_mapping(path.name, identifier, raw)
        for identifier, raw in sorted(raw_jobs.items())
        if isinstance(raw, dict)
    )
    return Workflow(
        name=path.name, path=path, triggers=_triggers(document), jobs=jobs
    )


def load_workflows() -> tuple[Workflow, ...]:
    """Load every workflow document under ``.github/workflows``."""
    paths = sorted(
        path
        for path in WORKFLOW_DIRECTORY.iterdir()
        if path.suffix in {".yml", ".yaml"}
    )
    return tuple(_workflow_from_path(path) for path in paths)


def iter_jobs(workflows: tuple[Workflow, ...]) -> Iterator[Job]:
    """Yield every job across the supplied workflows."""
    for workflow in workflows:
        yield from workflow.jobs


def iter_steps(workflows: tuple[Workflow, ...]) -> Iterator[tuple[Job, Step]]:
    """Yield every ``(job, step)`` pair across the supplied workflows."""
    for job in iter_jobs(workflows):
        for step in job.steps:
            yield job, step


def cache_paths(step: Step) -> tuple[str, ...]:
    """Return the normalized cache paths a cache step declares."""
    raw = step.inputs.get("path")
    if not isinstance(raw, str):
        return ()
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def registered_self_hosted_labels() -> frozenset[str]:
    """Return the runner labels registered with actionlint."""
    if not ACTIONLINT_CONFIG.exists():
        return frozenset()
    document = yaml.safe_load(ACTIONLINT_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return frozenset()
    runner = document.get("self-hosted-runner")
    labels = runner.get("labels") if isinstance(runner, dict) else None
    if not isinstance(labels, list):
        return frozenset()
    return frozenset(label for label in labels if isinstance(label, str))
