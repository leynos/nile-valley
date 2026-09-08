"""Shared execution helpers for Makefile gate scripts.

A Make recipe line that chains several tools in one shell reports only the
last tool's exit status, so an earlier failure is discarded. Gate logic
therefore lives in Python scripts that Make invokes as a single command.
These helpers give every such script one way to check tool availability, run
tools in order, stop at the first failure, and name the tool that failed.
"""

from __future__ import annotations

import contextlib
import dataclasses as dc
import subprocess
import sys
import typing as typ
from pathlib import Path

from plumbum import local
from plumbum.commands.base import BaseCommand
from plumbum.commands.processes import CommandNotFound

if typ.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

SUCCESS_EXIT_CODES: tuple[int, ...] = (0,)


class GateError(RuntimeError):
    """Raised when a gate tool is unavailable or exits unexpectedly.

    The message names the tool so the failure is actionable from a CI log.
    """


def tool_path(name: str) -> Path | None:
    """Return the resolved path of ``name``, or ``None`` when it is absent.

    Examples
    --------
    >>> tool_path("definitely-not-a-real-tool") is None
    True
    """
    try:
        return Path(str(local.which(name)))
    except CommandNotFound:
        return None


def require_tools(names: Iterable[str]) -> None:
    """Raise :class:`GateError` when any tool in ``names`` is not installed.

    Every missing tool is named at once so a single run reports the whole
    remediation, rather than one tool per failed invocation.

    Examples
    --------
    >>> require_tools([])
    """
    missing = [name for name in names if tool_path(name) is None]
    if missing:
        listed = ", ".join(missing)
        message = f"required tool(s) not installed: {listed}"
        raise GateError(message)


def require_env(values: Mapping[str, str | None], *, because: str) -> None:
    """Raise :class:`GateError` when any mapped value is unset or empty.

    Parameters
    ----------
    values:
        Environment variable names mapped to their current values.
    because:
        Explains the condition that makes the variables mandatory; it is
        appended to the error so the operator knows why they are needed.

    Examples
    --------
    >>> require_env({"HOME": "/root"}, because="always")
    """
    missing = [name for name, value in values.items() if not value]
    if missing:
        listed = ", ".join(missing)
        message = f"missing required environment variable(s) {listed} {because}"
        raise GateError(message)


@dc.dataclass(frozen=True, slots=True)
class ToolRun:
    """Where and how one tool invocation runs.

    Attributes
    ----------
    cwd:
        Directory the tool runs in; the caller's directory when ``None``.
    env:
        Environment overrides applied for the invocation alone.
    allowed_exit_codes:
        Statuses treated as success. OpenTofu's ``-detailed-exitcode`` returns
        ``2`` for pending changes, which is not a failure.
    label:
        Names the step in the error, distinguishing two steps that share a
        binary such as ``tofu validate`` and ``tofu plan``.
    stdin_text:
        Fed to the tool on standard input; input is closed when ``None``.
    stdin_path:
        Read into the tool's standard input, for output too large to hold in
        memory. It takes precedence over ``stdin_text``.

    Examples
    --------
    >>> ToolRun(label="tofu plan", allowed_exit_codes=(0, 2)).label
    'tofu plan'
    """

    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    allowed_exit_codes: Sequence[int] = SUCCESS_EXIT_CODES
    label: str | None = None
    stdin_text: str | None = None
    stdin_path: Path | None = None


@contextlib.contextmanager
def _execution_context(
    cwd: Path | None, env: Mapping[str, str] | None
) -> typ.Iterator[None]:
    """Apply the working directory and environment overrides for one command."""
    with contextlib.ExitStack() as stack:
        if cwd is not None:
            stack.enter_context(local.cwd(cwd))
        if env:
            stack.enter_context(local.env(**env))
        yield


def _flush_streams() -> None:
    """Flush this process's streams before a child writes to them."""
    # Python buffers standard output when it is redirected, so without this
    # the gate's own messages appear after the tool output they introduce.
    sys.stdout.flush()
    sys.stderr.flush()


def _check_status(status: int, name: str, run: ToolRun) -> int:
    """Return ``status`` or raise :class:`GateError` naming the failing tool."""
    if status not in tuple(run.allowed_exit_codes):
        message = f"{run.label or name} failed with exit status {status}"
        raise GateError(message)
    return status


@contextlib.contextmanager
def _stdin_target(run: ToolRun) -> typ.Iterator[tuple[typ.Any, bytes | None]]:
    """Yield the child's standard input and any payload to write to it."""
    # Standard input is closed unless the caller supplies one, so a tool that
    # reads a terminal fails fast instead of leaving the gate blocked.
    if run.stdin_path is not None:
        with run.stdin_path.open("rb") as handle:
            yield handle, None
    elif run.stdin_text is not None:
        yield subprocess.PIPE, run.stdin_text.encode("utf-8")
    else:
        yield subprocess.DEVNULL, None


@contextlib.contextmanager
def _stdout_target(destination: Path | None, *, capture: bool) -> typ.Iterator[typ.Any]:
    """Yield the child's standard output: a file, a pipe, or this process's."""
    if destination is not None:
        with destination.open("wb") as handle:
            yield handle
    else:
        yield subprocess.PIPE if capture else None


def _spawn(
    command: BaseCommand,
    run: ToolRun,
    *,
    destination: Path | None = None,
    capture: bool = False,
) -> tuple[int, bytes]:
    """Run ``command`` under ``run`` and return its status and any output."""
    _flush_streams()
    with (
        _execution_context(run.cwd, run.env),
        _stdin_target(run) as (stdin, payload),
        _stdout_target(destination, capture=capture) as stdout,
    ):
        process = command.popen(stdin=stdin, stdout=stdout, stderr=None)
        captured, _ = process.communicate(input=payload)
    return process.returncode, captured or b""


def run_tool(name: str, args: Sequence[str] = (), run: ToolRun | None = None) -> int:
    """Run ``name`` with ``args`` and return its exit status.

    Output is inherited rather than captured so the gate log reads exactly as
    it would when the tool is run by hand. A status outside the run's allowed
    exit codes raises :class:`GateError` naming the tool, which stops the
    caller before it runs the next tool in the sequence.

    Examples
    --------
    >>> run_tool("true")
    0
    """
    run = run or ToolRun()
    status, _ = _spawn(local[name][tuple(args)], run)
    return _check_status(status, name, run)


def write_tool_output(
    name: str,
    args: Sequence[str] = (),
    *,
    destination: Path,
    run: ToolRun | None = None,
) -> int:
    """Run ``name`` with its standard output redirected into ``destination``.

    This is the path for a tool whose output is a generated artefact rather
    than a diagnostic: an OpenTofu plan in JSON, or a rendered chart. The
    bytes never enter this process, so the size of the artefact does not
    become the gate's memory footprint.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as raw:
    ...     out = Path(raw) / "rendered"
    ...     write_tool_output("echo", ["rendered"], destination=out)
    ...     out.read_text(encoding="utf-8").strip()
    0
    'rendered'
    """
    run = run or ToolRun()
    status, _ = _spawn(local[name][tuple(args)], run, destination=destination)
    return _check_status(status, name, run)


def capture_tool(
    name: str, args: Sequence[str] = (), run: ToolRun | None = None
) -> str:
    """Run ``name`` and return its standard output as text.

    Only for output that is bounded by construction, such as a list of tracked
    files. Use :func:`write_tool_output` for a generated artefact, whose size
    is set by the thing being generated rather than by the repository.

    Diagnostics still reach the gate log because standard error is inherited.
    A disallowed exit status raises :class:`GateError` naming the tool, so the
    caller never feeds the output of a failed command into the next step.

    Examples
    --------
    >>> capture_tool("echo", ["rendered"]).strip()
    'rendered'
    """
    run = run or ToolRun()
    status, stdout = _spawn(local[name][tuple(args)], run, capture=True)
    _check_status(status, name, run)
    return stdout.decode("utf-8")


def skip(message: str) -> None:
    """Report that a gate is intentionally not running.

    Examples
    --------
    >>> skip("Skipping example gate; set EXAMPLE_PATH to enable")
    Skipping example gate; set EXAMPLE_PATH to enable
    """
    print(message, flush=True)


def run_gate(entry_point: Callable[[], object]) -> typ.NoReturn:
    """Invoke ``entry_point`` and translate a :class:`GateError` into exit 1.

    Scripts call this from ``__main__`` so a failing tool produces a one-line
    diagnostic instead of a traceback, while unexpected exceptions still
    surface in full.

    Examples
    --------
    >>> run_gate(lambda: None)
    Traceback (most recent call last):
    SystemExit: 0
    """
    try:
        entry_point()
    except GateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(0)
