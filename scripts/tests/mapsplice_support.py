"""Ask `mapsplice` itself what the roadmap grammar is.

The patterns in :mod:`scripts.tests.roadmap_grammar_support` restate the
grammar, and a restatement cannot show that it is what the tool enforces. This
module runs the tool, so the tests can put the two readings side by side: a
heading the patterns call well formed must be one the tool accepts, and one
they call legacy must be one the tool rejects.

`mapsplice` is not installed in CI, so nothing here is called unconditionally.
The examples below are marked ``+SKIP`` for the same reason: the documented-
example gate runs them wherever the suite runs, and an example that shelled
out to an absent binary would fail the gate on a machine that has been
configured correctly.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import typing as typ
from pathlib import Path

from scripts.tests.roadmap_grammar_support import ROADMAP_PATH, fragment, read

MAPSPLICE = "mapsplice"

# `mapsplice` reports through a structured log and colours its output, so the
# escape sequences are stripped to leave a reason a failure can print.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
REASON = re.compile(r"invalid_roadmap.*", re.DOTALL)

# A roadmap holding one canonical phase and step. Grammar probes append to a
# copy of this rather than to the real document, so a probe reports on the
# fragment it was given and never on whether the document happens to be sound.
GRAMMAR_PROBE = "## 1. Probe phase\n\n### 1.1. Probe step\n"


@contextlib.contextmanager
def copied(path: Path) -> typ.Iterator[Path]:
    """Yield a writable copy of ``path`` inside a temporary directory.

    `mapsplice append` rewrites its target, so every probe runs against a copy
    and the document under test is never modified.

    Examples
    --------
    >>> # with copied(ROADMAP_PATH) as working: ...
    """
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        duplicate = Path(directory) / path.name
        duplicate.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        yield duplicate


def _append(fragment_text: str, roadmap: Path) -> tuple[int, str]:
    """Append ``fragment_text`` to a copy of ``roadmap`` and report the result.

    The tool reports through its status and its log, so both are returned.

    Examples
    --------
    >>> _append(GRAMMAR_PROBE, ROADMAP_PATH)  # doctest: +SKIP
    """
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "fragment.md"
        source.write_text(fragment_text, encoding="utf-8")
        with copied(roadmap) as working:
            completed = subprocess.run(  # noqa: S603
                [MAPSPLICE, "append", str(working), str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
    cleaned = ANSI.sub("", completed.stderr)
    found = REASON.search(cleaned)
    reason = (found.group(0) if found else cleaned).strip()
    return completed.returncode, reason


def rejects_text(text: str) -> tuple[int, str]:
    """Report the tool's verdict on a standalone roadmap-shaped ``text``.

    ``text`` is offered as a fragment against a minimal canonical roadmap, so
    a heading form the tool does not recognise is reported by the tool itself
    rather than only by the patterns. The probe is self-contained: it answers
    for the grammar alone, and never for the state of the real document.

    Examples
    --------
    >>> rejects_text("## 1. Fine\\n\\n### 1.1. Fine\\n")  # doctest: +SKIP
    """
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        probe = Path(directory) / "probe.md"
        probe.write_text(GRAMMAR_PROBE, encoding="utf-8")
        return _append(fragment(text), probe)


def validates(path: Path | None = None) -> tuple[int, str]:
    """Report whether the roadmap as committed is well formed, per `mapsplice`.

    The document's own phase-onward body is appended to a copy of it, so the
    status is a verdict on the heading grammar of the file itself.

    Examples
    --------
    >>> validates()  # doctest: +SKIP
    """
    document = path or ROADMAP_PATH
    return _append(fragment(read(document)), document)


def available() -> bool:
    """Return whether the `mapsplice` binary is on ``PATH``.

    Examples
    --------
    >>> available()  # doctest: +SKIP
    True
    """
    return shutil.which(MAPSPLICE) is not None
