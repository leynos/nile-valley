"""Helpers for reading GitHub Actions workflows in contract tests.

The workflow contracts assert structural properties of every workflow in
``.github/workflows``. These helpers turn the raw YAML into small, typed
records so each contract test can state one property without re-parsing the
documents.

Examples
--------
>>> workflows = load_workflows()  # doctest: +SKIP
>>> sorted(workflow.name for workflow in workflows)  # doctest: +SKIP
['ci.yml', 'delayed-pr-comment.yml', 'dependabot-automerge.yml']
"""

from __future__ import annotations

import dataclasses as dc
import typing as typ
from pathlib import Path

import yaml

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
    "load_workflows",
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
    runs_on: str
    uses: str
    timeout_minutes: int | None
    steps: tuple[Step, ...]

    @property
    def qualified_name(self) -> str:
        """Return a stable ``workflow.yml:job`` label for assertion messages."""
        return f"{self.workflow}:{self.identifier}"


@dc.dataclass(frozen=True)
class Workflow:
    """A parsed workflow document."""

    name: str
    path: Path
    jobs: tuple[Job, ...]


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


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
    return Job(
        workflow=workflow,
        identifier=identifier,
        runs_on=_as_text(raw.get("runs-on")),
        uses=_as_text(raw.get("uses")),
        timeout_minutes=timeout if isinstance(timeout, int) else None,
        steps=steps,
    )


def _workflow_from_path(path: Path) -> Workflow:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_jobs = document.get("jobs", {}) if isinstance(document, dict) else {}
    jobs = tuple(
        _job_from_mapping(path.name, identifier, raw)
        for identifier, raw in sorted(raw_jobs.items())
        if isinstance(raw, dict)
    )
    return Workflow(name=path.name, path=path, jobs=jobs)


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
