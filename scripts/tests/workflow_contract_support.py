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
import re
import typing as typ
from pathlib import Path

import yaml
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
    "branch_filter_admits",
    "cache_paths",
    "iter_jobs",
    "iter_steps",
    "load_workflows",
    "runner_labels",
    "registered_self_hosted_labels",
]


_CLASS_MEMBER: typ.Final = re.compile(r"[A-Za-z0-9-]+\Z")


def _read_character_class(pattern: str, index: int) -> tuple[str, int] | None:
    """Return the regex for a bracket class at ``index``, and the index after it.

    None means the brackets are not a class GitHub documents, so the
    caller reads the `[` literally rather than guessing at a meaning.
    GitHub's class holds alphanumerics and ranges of them and nothing
    else, so a bracket carrying anything further is a branch name that
    happens to contain a bracket.

    Parameters
    ----------
    pattern : str
        The whole filter pattern.
    index : int
        The offset of the opening bracket.

    Returns
    -------
    tuple[str, int] or None
        The class and the offset after its closing bracket, or None.

    Examples
    --------
    >>> _read_character_class("m[ai]n", 1)
    ('[ai]', 5)
    >>> _read_character_class("m[a/b]n", 1) is None
    True
    >>> _read_character_class("m[ain", 1) is None
    True
    """
    close = pattern.find("]", index + 1)
    if close == -1:
        return None
    members = pattern[index + 1 : close]
    if not _CLASS_MEMBER.match(members):
        return None
    return f"[{members}]", close + 1


def _quantify(parts: list[str], quantifier: str) -> None:
    """Apply ``quantifier`` to the last atom emitted, or emit it literally.

    GitHub's `?` and `+` bind to the character before them rather than
    standing for one character and for one or more. With nothing before
    them there is nothing to repeat, so the character is a literal.

    Parameters
    ----------
    parts : list[str]
        The regex fragments built so far, modified in place.
    quantifier : str
        Either `?` or `+`.

    Examples
    --------
    >>> parts = ["a"]
    >>> _quantify(parts, "?")
    >>> parts
    ['(?:a)?']
    >>> parts = []
    >>> _quantify(parts, "+")
    >>> parts
    ['\\\\+']
    """
    if not parts:
        parts.append(re.escape(quantifier))
        return
    parts[-1] = f"(?:{parts[-1]}){quantifier}"


def _filter_pattern(pattern: str) -> re.Pattern[str]:
    """Return ``pattern`` as GitHub reads a branch filter.

    `fnmatch` is not a stand-in for this, and the comment that said it
    was had the direction of harm backwards. GitHub's `*` matches
    within a path segment and its `**` crosses `/`; `fnmatch`'s `*`
    crosses `/` always. So `fnmatch` matches `release/*` against
    `release/a/b` where GitHub does not, and the reader then reported a
    workflow as reaching trunk automatically when no push to trunk
    would start a run. That is a reachability contract passing on
    exactly the workflow it exists to fail, which is the opposite of
    the "errs towards admitting" claim that was written here.

    The rest of the grammar is GitHub's own: `?` matches zero or one of
    the preceding character and `+` one or more of it, so both bind to
    what came before rather than standing for a character of their own;
    `[]` is a class of alphanumerics and ranges; and `\\` escapes the
    character after it. An earlier reading treated `?` as exactly one
    character and escaped the brackets, so `main?` admitted `mains` and
    refused `main`, and `m[ai]n` refused `man`: each the wrong way
    round, and each a branch filter read as covering a set of branches
    that it does not.

    Parameters
    ----------
    pattern : str
        A `branches` or `branches-ignore` entry, without any leading `!`.

    Returns
    -------
    re.Pattern[str]
        A pattern anchored at both ends.

    Examples
    --------
    >>> bool(_filter_pattern("release/*").fullmatch("release/a"))
    True
    >>> bool(_filter_pattern("release/*").fullmatch("release/a/b"))
    False
    >>> bool(_filter_pattern("release/**").fullmatch("release/a/b"))
    True
    >>> bool(_filter_pattern("mai?n").fullmatch("main"))
    True
    >>> bool(_filter_pattern("mai+n").fullmatch("maiin"))
    True
    >>> bool(_filter_pattern("m[ai]n").fullmatch("man"))
    True
    >>> bool(_filter_pattern("m[ai]n").fullmatch("main"))
    False
    """
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\" and index + 1 < len(pattern):
            parts.append(re.escape(pattern[index + 1]))
            index += 2
            continue
        if char == "*":
            crosses_a_separator = pattern.startswith("**", index)
            parts.append(".*" if crosses_a_separator else "[^/]*")
            index += 2 if crosses_a_separator else 1
            continue
        if char in "?+":
            _quantify(parts, char)
            index += 1
            continue
        if char == "[":
            read = _read_character_class(pattern, index)
            if read is not None:
                member_class, index = read
                parts.append(member_class)
                continue
        parts.append(re.escape(char))
        index += 1
    return re.compile("".join(parts))


def _last_verdict(branch: str, patterns: object) -> bool | None:
    """Return the verdict of the last pattern ``branch`` matches, or None.

    GitHub evaluates a filter in the order it is written: a later `!`
    pattern excludes a branch an earlier one admitted, and a later
    positive pattern admits it again. Reporting "any pattern matches"
    instead read `["**", "!main"]` as admitting `main`, so a workflow
    whose push filter excludes trunk was reported as reaching trunk
    automatically and its trunk-guarded cache saves passed the
    reachability contract while nothing could run them.

    None means no pattern matched at all, which the caller reads
    differently for the two filter keys.

    Parameters
    ----------
    branch : str
        A branch's short name.
    patterns : object
        The raw value of a `branches` or `branches-ignore` key.

    Returns
    -------
    bool or None
        Whether the last matching pattern admits, or None if none match.

    Examples
    --------
    >>> _last_verdict("main", ["main"])
    True
    >>> _last_verdict("main", ["**", "!main"])
    False
    >>> _last_verdict("main", ["**", "!main", "main"])
    True
    >>> _last_verdict("main", ["releases/**"]) is None
    True
    >>> _last_verdict("main", "main") is None
    True
    """
    if not isinstance(patterns, list):
        return None
    verdict: bool | None = None
    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        admits = not pattern.startswith("!")
        expression = pattern if admits else pattern[1:]
        if _filter_pattern(expression).fullmatch(branch) is not None:
            verdict = admits
    return verdict


def branch_filter_admits(event: dict[str, object], branch: str) -> bool:
    """Report whether an event's branch filters let ``branch`` start a run.

    Both filters are read, because either alone decides the question.
    `branches-ignore` excludes outright: a `push` that ignores `main`
    starts no run for a push to `main`, however the rest of the trigger
    is written, and reading only `branches` reported such a workflow as
    reaching trunk automatically. `branches` restricts: present, it is
    the whole admitted set; absent, every branch is admitted.

    GitHub refuses a workflow that declares both filters for one event,
    so the two cannot disagree in a document that runs at all.

    The patterns are read as GitHub reads them rather than through
    `fnmatch`; see `_filter_pattern` for why that difference decides a
    contract rather than a corner case. Within one key they are read in
    order, so a later `!` entry excludes what an earlier entry admitted;
    see `_last_verdict`.

    Parameters
    ----------
    event : dict[str, object]
        The mapping under a trigger such as `push`.
    branch : str
        The branch's short name.

    Returns
    -------
    bool
        Whether a push to ``branch`` starts a run.

    Examples
    --------
    >>> branch_filter_admits({"branches": ["main"]}, "main")
    True
    >>> branch_filter_admits({"branches-ignore": ["main"]}, "main")
    False
    >>> branch_filter_admits({}, "main")
    True
    >>> branch_filter_admits({"branches": ["**", "!main"]}, "main")
    False
    >>> branch_filter_admits({"branches": ["**", "!main", "ma?in"]}, "main")
    True
    """
    if _last_verdict(branch, event.get("branches-ignore")) is True:
        return False
    branches = event.get("branches")
    if branches is None:
        return True
    return _last_verdict(branch, branches) is True


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
