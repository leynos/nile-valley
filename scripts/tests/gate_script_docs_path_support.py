"""Reading the filesystem paths the documented examples name.

Split from :mod:`scripts.tests.gate_script_docs_support` because the
questions are different. That module decides which modules the gate
covers and runs their examples; this one reads a source for the absolute
paths its examples mention, and reads the filesystem for whether running
them changed anything.

The rules take a source string rather than a module name wherever they
can, so a test can drive them with a source written to violate them.
Parametrised over the repository's own modules a rule can only fail on a
regression, and a mutation that removes it survives.
"""

from __future__ import annotations

import re
import stat
import tempfile
from pathlib import Path

from scripts.tests.gate_script_docs_support import EXECUTED_MODULES, REPOSITORY_ROOT

#: Directories every process on the machine shares. An example that
#: names one of these as somewhere to write cannot be watched: their
#: contents change constantly for unrelated reasons, so a gate that
#: compared them would fail on another process's file. They are refused
#: instead of watched.
SHARED_ROOTS = frozenset(
    {
        Path(tempfile.gettempdir()),
        Path("/tmp"),
        Path("/var/tmp"),
    }
)

#: A quoted absolute filesystem path appearing in an example. A URL is
#: quoted and contains a slash too, so a scheme-relative `//` is
#: excluded rather than the leading slash being taken as proof.
_ABSOLUTE_IN_AN_EXAMPLE = re.compile(r"""["'](/[^"'\s]*)["']""")


def _absolute_literals_in(module_name: str) -> list[str]:
    """Return the absolute path literals one module's examples mention.

    Reads the source rather than running it: both callers need the list
    before anything is executed, one to watch those paths and one to
    refuse some of them outright.

    Parameters
    ----------
    module_name : str
        The dotted module name.

    Returns
    -------
    list[str]
        The literals, in the order they appear.
    """
    path = REPOSITORY_ROOT / Path(*module_name.split(".")).with_suffix(".py")
    return absolute_literals_in_source(path.read_text(encoding="utf-8"))


def absolute_literals_in_source(source: str) -> list[str]:
    """Return the absolute path literals the examples in ``source`` mention.

    Split from the module reader so the rule can be exercised against a
    source written for the purpose. Parametrised over the repository's
    own modules it can only fail on a regression, which means a mutation
    that removes it survives, which means nothing shows the rule works.

    Parameters
    ----------
    source : str
        Python source.

    Returns
    -------
    list[str]
        The literals, in the order they appear.
    """
    found: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith((">>> ", "... ")):
            continue
        # A commented example is inert text; `doctest` never runs it.
        if stripped[4:].lstrip().startswith("#"):
            continue
        found.extend(
            literal
            for literal in _ABSOLUTE_IN_AN_EXAMPLE.findall(stripped)
            if not literal.startswith("//")
        )
    return found


def shared_roots_named_in_source(source: str) -> list[str]:
    """Return the shared temporary roots the examples in ``source`` name.

    One place, called by the rule over the repository's modules and by
    the test that drives it with a source written to violate it. Keeping
    the membership test here is what lets the second prove the first:
    with it inlined in the rule, nothing exercised it, because no module
    in the repository names one.

    Parameters
    ----------
    source : str
        Python source.

    Returns
    -------
    list[str]
        The offending literals, in the order they appear.
    """
    return [
        literal
        for literal in absolute_literals_in_source(source)
        if Path(literal) in SHARED_ROOTS
    ]


def absolute_paths_named_in_examples() -> tuple[Path, ...]:
    """Return every absolute path the discovered examples mention.

    Reads the source rather than running it, because this is the list a
    later assertion watches while the examples run. Read over every
    module the gate executes, the suite's support modules included: an
    example of theirs runs like any other, so a path named only there
    would otherwise be written unwatched.

    Most of these are inert: a path handed to a value object that
    nothing writes is named but never touched, which is why naming one
    is not itself the offence. What matters is which of them exist
    afterwards.

    Returns
    -------
    tuple[Path, ...]
        The paths, deduplicated, in a stable order.
    """
    found: set[str] = set()
    for module_name in EXECUTED_MODULES:
        found.update(_absolute_literals_in(module_name))
    return tuple(Path(name) for name in sorted(found))


def signature_of(path: Path) -> object | None:
    """Return a value that changes if ``path`` is created or written.

    Existence alone is not enough. This gate first ran green on a host
    where an earlier run had already made the files, so the run that
    made them again looked like it had made nothing; the same check
    failed on CI's clean machine. History must not be able to mask the
    run.

    A directory is compared by existence only. The ones named here are
    shared, `/tmp` among them, and their modification time moves
    whenever anything else on the machine touches them.

    Parameters
    ----------
    path : Path
        The path to read.

    Returns
    -------
    object or None
        None when absent, a marker for a directory, and the size and
        modification time for a file.
    """
    try:
        status = path.stat()
    except OSError:
        return None
    if stat.S_ISDIR(status.st_mode):
        if path in SHARED_ROOTS:
            # Compared by existence alone. These are shared with every
            # other process on the machine, so their contents and their
            # modification time move for reasons that have nothing to do
            # with this run, and watching them would make the gate
            # flaky, which is worse than the gap.
            #
            # The gap is real: a write to a path derived beneath one of
            # these, rather than named outright, is invisible here.
            # `test_no_example_names_a_shared_temporary_root` is what
            # closes it, by refusing the only way an example can reach
            # one.
            return "a shared directory"
        # Named and not shared, so its contents are this run's business.
        # An example that writes a derived file beneath a directory it
        # named is caught here rather than by its own name.
        return sorted(str(child.relative_to(path)) for child in path.rglob("*"))
    return (status.st_size, status.st_mtime_ns)
