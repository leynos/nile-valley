"""Helpers for asserting that CI actually runs the Make gates.

A workflow contract that only finds a command inside a step's ``run`` value
certifies a step that may never execute. The command survives a wrapper, a
``|| true`` suffix, and a condition on the step or the job, so this module
checks the whole shape instead: the job exists, some step's entire ``run`` is
the gate command, and neither the job nor that step carries a condition.

Conditions are detected by the presence of the ``if`` key, never by its value.
YAML parses ``if: false`` to a boolean and ``if: 'false'`` to a string, and a
plausible condition such as a push-only one is not falsy at all, so any
condition disqualifies the step.
"""

from __future__ import annotations

import copy
import typing as typ

import yaml
from workflow_contract_support import WORKFLOW_DIRECTORY

if typ.TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

CI_WORKFLOW = WORKFLOW_DIRECTORY / "ci.yml"
CONDITION_KEY = "if"
# PyYAML resolves the bare key `on` to True under YAML 1.1, so a document that
# quotes it and one that does not parse to different keys.
TRIGGER_KEYS = ("on", True)

Document = dict[typ.Any, typ.Any]


def load_document(path: Path | None = None) -> Document:
    """Parse a workflow document.

    Examples
    --------
    >>> load_document()["name"]
    'ci'
    """
    parsed = yaml.safe_load((path or CI_WORKFLOW).read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def triggers(document: Mapping[typ.Any, typ.Any]) -> frozenset[str]:
    """Return the event names the workflow reacts to.

    Examples
    --------
    >>> "pull_request" in triggers(load_document())
    True
    """
    for key in TRIGGER_KEYS:
        raw = document.get(key)
        if isinstance(raw, dict):
            return frozenset(str(event) for event in raw)
        if isinstance(raw, list):
            return frozenset(str(event) for event in raw)
        if isinstance(raw, str):
            return frozenset({raw})
    return frozenset()


def _jobs(document: Mapping[typ.Any, typ.Any]) -> Iterator[tuple[str, Document]]:
    """Yield each job identifier and its mapping."""
    raw = document.get("jobs")
    if not isinstance(raw, dict):
        return
    for identifier, job in raw.items():
        if isinstance(job, dict):
            yield str(identifier), job


def _steps(job: Mapping[str, typ.Any]) -> Iterator[Document]:
    """Yield each step mapping of a job."""
    raw = job.get("steps")
    if not isinstance(raw, list):
        return
    for step in raw:
        if isinstance(step, dict):
            yield step


class GateStep(typ.NamedTuple):
    """A step whose whole ``run`` is the gate command, and its job."""

    job_identifier: str
    job: Document
    step: Document


def matching_steps(
    document: Mapping[typ.Any, typ.Any], command: str
) -> Iterator[GateStep]:
    """Yield every step whose entire ``run`` is ``command``.

    Comparing the whole value is the point: a wrapper or a ``|| true`` suffix
    leaves the command in the file while stopping it from deciding anything.

    Examples
    --------
    >>> found = matching_steps(load_document(), "make lint")
    >>> [gate.job_identifier for gate in found]
    ['build']
    """
    for identifier, job in _jobs(document):
        for step in _steps(job):
            if str(step.get("run", "")).strip() == command:
                yield GateStep(job_identifier=identifier, job=job, step=step)


def _first_match(document: Document, command: str) -> GateStep:
    """Return the first step running ``command``, or raise."""
    for found in matching_steps(document, command):
        return found
    message = f"no step's whole run is {command!r}"
    raise LookupError(message)


def gate_failures(document: Mapping[typ.Any, typ.Any], command: str) -> list[str]:
    """Return the reasons ``command`` is not run unconditionally on a pull request.

    An empty list means some unconditional step of an unconditional job runs
    exactly ``command``, and the workflow reacts to ``pull_request``.

    Examples
    --------
    >>> gate_failures(load_document(), "make lint")
    []
    """
    reasons: list[str] = []
    if "pull_request" not in triggers(document):
        reasons.append("the workflow does not react to pull_request")

    matched = False
    for found in matching_steps(document, command):
        matched = True
        if CONDITION_KEY in found.job:
            reasons.append(f"job {found.job_identifier} carries a condition")
        elif CONDITION_KEY in found.step:
            reasons.append(f"the step running {command!r} carries a condition")
        else:
            return reasons

    if not matched:
        reasons.append(f"no step's whole run is {command!r}")
    return reasons


def with_mutation(
    document: Document, mutate: typ.Callable[[Document], None]
) -> Document:
    """Return a copy of ``document`` with ``mutate`` applied.

    Examples
    --------
    >>> mutated = with_mutation(load_document(), lambda doc: doc.pop("jobs"))
    >>> "jobs" in mutated
    False
    """
    duplicate = copy.deepcopy(document)
    mutate(duplicate)
    return duplicate


def find_step(document: Document, command: str) -> Document:
    """Return the step whose whole ``run`` is ``command``.

    Examples
    --------
    >>> find_step(load_document(), "make lint")["name"]
    'Lint'
    """
    return _first_match(document, command).step


def find_job(document: Document, command: str) -> Document:
    """Return the job holding the step whose whole ``run`` is ``command``.

    Examples
    --------
    >>> "steps" in find_job(load_document(), "make lint")
    True
    """
    return _first_match(document, command).job
