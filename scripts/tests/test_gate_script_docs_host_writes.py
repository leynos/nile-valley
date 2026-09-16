"""Running the documented examples must not touch the host.

Split from :mod:`scripts.tests.test_gate_script_docs`, which asks which
modules the gate covers. These ask what running their examples does to
the filesystem: that none hands a shared temporary root to anything,
that a run creates nothing at the absolute paths the examples name, and
that the isolation puts a relative write in a scratch directory and the
process back where it found it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.tests.gate_script_docs_path_support import (
    absolute_paths_named_in_examples,
    shared_roots_named_in_source,
    signature_of,
)
from scripts.tests.gate_script_docs_support import (
    CHECKED_MODULES,
    GATE_MODULES,
    KNOWN_STALE_EXAMPLES,
    REPOSITORY_ROOT,
    in_a_scratch_directory,
    run_examples,
)


@pytest.mark.parametrize("module_name", GATE_MODULES, ids=str)
def test_no_example_names_a_shared_temporary_root(module_name: str) -> None:
    """No example may hand a shared temporary directory to anything.

    This is the one gap the host-write check cannot close by watching.
    A shared root is compared by existence, because its contents move
    for reasons unrelated to this run, so a file written to a path
    derived beneath one is invisible: an example passing
    ``runner_temp=Path("/tmp")`` had the code beneath it create
    ``/tmp/render-manifests/platform.tfvars.json`` on every run of this
    suite, and the watch said nothing.

    Refusing the root closes it, because a derived path can only escape
    into a directory the example named. The remedy is the same as
    everywhere else here: make a temporary directory, and then the
    example can also assert what it produced.
    """
    path = REPOSITORY_ROOT / Path(*module_name.split(".")).with_suffix(".py")
    named = set(shared_roots_named_in_source(path.read_text(encoding="utf-8")))

    assert not named, (
        f"{module_name} hands a shared temporary directory to an example: "
        f"{sorted(str(path) for path in named)}. Anything written beneath it "
        "cannot be watched. Use a tempfile.TemporaryDirectory instead."
    )


def test_running_every_example_creates_nothing_on_the_host() -> None:
    """Executing the examples leaves the paths they name as it found them.

    This is the half of the write boundary that isolation cannot
    provide. Running from a temporary directory contains a relative
    write and contains nothing at all about an absolute one: two
    examples here named `/tmp/vars.tfvars.json` and `/tmp/out` and
    created them on every run of this suite, on a machine the gate
    shares with everything else. No sandbox available to a test can
    stop that, so what the run creates is watched instead.

    Naming an absolute path is not the offence, which is why this
    watches the paths rather than the mentions. Most of those named
    here are handed to a value object that nothing writes, and they
    stay absent whatever the example does with them.
    """
    watched = absolute_paths_named_in_examples()
    assert watched, "no example names an absolute path; this now asserts nothing"
    before = {path: signature_of(path) for path in watched}

    for module_name in (*CHECKED_MODULES, *sorted(KNOWN_STALE_EXAMPLES)):
        run_examples(module_name)

    touched = sorted(
        str(path) for path in watched if signature_of(path) != before[path]
    )

    assert not touched, (
        f"running the examples wrote {touched} on the host. An example that "
        "needs a file should make its own tempfile.TemporaryDirectory, which "
        "also lets it assert what it produced instead of asserting nothing."
    )


#: What the disposable-directory test's purpose-built example writes.
#: Named once because the test both creates it and looks for it in two
#: places, and a disagreement between those spellings would make the
#: test pass by looking for the wrong thing.
WITNESS = "left-behind-by-an-example"


def test_the_examples_are_run_from_somewhere_disposable(tmp_path: Path) -> None:
    """`run_examples` executes its examples outside the repository.

    Asserted through `run_examples` rather than through the context
    manager it uses, because removing the isolation from `run_examples`
    while leaving the helper intact is a one-line edit that a test of
    the helper alone would not notice.

    A module is written for the purpose: its example writes a relative
    file, so where that file lands is where the examples ran.

    The landing sites are cleared first. Proving this by mutation means
    deliberately running the gate without its isolation, which leaves
    the very file this looks for; without the clearing, the next honest
    run then fails on the last dishonest one's litter and says the
    isolation is broken when it is not.
    """
    landings = (REPOSITORY_ROOT / WITNESS, tmp_path / WITNESS)
    for landing in landings:
        landing.unlink(missing_ok=True)

    module = tmp_path / "writes_relatively.py"
    module.write_text(
        '"""A module whose example writes beside the working directory.\n\n'
        "Examples\n--------\n"
        ">>> from pathlib import Path\n"
        f'>>> Path("{WITNESS}").write_text("x", encoding="utf-8")\n'
        "1\n"
        '"""\n',
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        outcome = run_examples("writes_relatively")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("writes_relatively", None)

    assert outcome.held, outcome.detail
    assert not (REPOSITORY_ROOT / WITNESS).exists(), (
        "the examples ran in the repository root"
    )
    assert not (tmp_path / WITNESS).exists(), (
        "the examples ran in the module's own directory"
    )


def test_running_the_examples_leaves_the_working_directory_alone() -> None:
    """The gate puts the process back where it found it.

    The isolation is a `chdir`, and a `chdir` that is not undone moves
    every test that runs after this one.
    """
    before = Path.cwd()

    for module_name in sorted(KNOWN_STALE_EXAMPLES)[:3]:
        run_examples(module_name)

    assert Path.cwd() == before, f"the gate left the process in {Path.cwd()}"


def test_an_example_that_writes_relatively_leaves_no_trace() -> None:
    """A write from an example lands in the scratch directory, not here.

    Two examples in the manifest writer named absolute paths under
    `/tmp` and created them on every run of this suite. Those are
    repaired at the source, but the next careless example is not
    hypothetical, so the isolation is asserted rather than trusted.
    """
    before = sorted(REPOSITORY_ROOT.iterdir())

    with in_a_scratch_directory() as scratch:
        Path("written-by-an-example").write_text("x", encoding="utf-8")
        assert (scratch / "written-by-an-example").exists(), (
            "the scratch directory is not where a relative write landed"
        )

    assert sorted(REPOSITORY_ROOT.iterdir()) == before, (
        "running the examples added something to the repository root"
    )
