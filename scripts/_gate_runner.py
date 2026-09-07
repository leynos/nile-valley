"""Shared execution helpers for Makefile gate scripts.

A Make recipe line that chains several tools in one shell reports only the
last tool's exit status, so an earlier failure is discarded. Gate logic
therefore lives in Python scripts that Make invokes as a single command.
These helpers give every such script one way to check tool availability, run
tools in order, stop at the first failure, and name the tool that failed.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import typing as typ
from pathlib import Path

from plumbum import local
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


def _check_status(
    status: int, name: str, label: str | None, allowed_exit_codes: Sequence[int]
) -> int:
    """Return ``status`` or raise :class:`GateError` naming the failing tool."""
    if status not in tuple(allowed_exit_codes):
        message = f"{label or name} failed with exit status {status}"
        raise GateError(message)
    return status


def run_tool(
    name: str,
    args: Sequence[str] = (),
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    allowed_exit_codes: Sequence[int] = SUCCESS_EXIT_CODES,
    label: str | None = None,
    stdin_text: str | None = None,
) -> int:
    """Run ``name`` with ``args`` and return its exit status.

    Output is inherited rather than captured so the gate log reads exactly as
    it would when the tool is run by hand. An exit status outside
    ``allowed_exit_codes`` raises :class:`GateError` naming the tool, which
    stops the caller before it runs the next tool in the sequence.

    ``allowed_exit_codes`` exists for OpenTofu's ``-detailed-exitcode``, where
    ``2`` means "changes pending" rather than failure.

    Standard input is closed unless ``stdin_text`` is supplied, so a tool that
    reads from a terminal fails fast instead of hanging a gate.

    Examples
    --------
    >>> run_tool("true")
    0
    """
    command = local[name][tuple(args)]
    with _execution_context(cwd, env):
        if stdin_text is None:
            process = command.popen(
                stdin=subprocess.DEVNULL, stdout=None, stderr=None
            )
            status = process.wait()
        else:
            process = command.popen(
                stdin=subprocess.PIPE, stdout=None, stderr=None
            )
            process.communicate(input=stdin_text.encode("utf-8"))
            status = process.returncode
    return _check_status(status, name, label, allowed_exit_codes)


def capture_tool(
    name: str,
    args: Sequence[str] = (),
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    allowed_exit_codes: Sequence[int] = SUCCESS_EXIT_CODES,
    label: str | None = None,
) -> str:
    """Run ``name`` and return its standard output as text.

    Diagnostics still reach the gate log because standard error is inherited.
    A disallowed exit status raises :class:`GateError` naming the tool, so the
    caller never feeds the output of a failed command into the next step.

    Examples
    --------
    >>> capture_tool("echo", ["rendered"]).strip()
    'rendered'
    """
    command = local[name][tuple(args)]
    with _execution_context(cwd, env):
        process = command.popen(
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=None
        )
        stdout, _ = process.communicate()
        status = process.returncode
    _check_status(status, name, label, allowed_exit_codes)
    return stdout.decode("utf-8") if isinstance(stdout, bytes) else str(stdout)


def skip(message: str) -> None:
    """Report that a gate is intentionally not running.

    Examples
    --------
    >>> skip("Skipping example gate; set EXAMPLE_PATH to enable")
    Skipping example gate; set EXAMPLE_PATH to enable
    """
    print(message)


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
