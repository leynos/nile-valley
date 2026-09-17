"""The documented-example gate's write rules, driven to breaking point.

Every rule in :mod:`scripts.tests.gate_script_docs_path_support` is
parametrised elsewhere over the repository's own modules, where it
passes because the sources are correct. A rule proved only that way
survives its own mutation. These drive the mechanisms directly against
inputs written to violate them.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from scripts.tests.gate_script_docs_path_support import (
    absolute_literals_in_source,
    shared_roots_named_in_source,
    signature_of,
)
from scripts.tests.gate_script_docs_support import (
    REPOSITORY_ROOT,
    Verdict,
    run_examples,
)


class TestTheRulesBiteOnSomethingWrittenToBreakThem:
    """Each guard is shown working, not merely shown passing.

    Parametrised over the repository's own modules, every rule here
    passes because the sources are correct, so removing the rule changes
    nothing and a mutation of it survives. These drive the mechanisms
    directly against inputs written to violate them.
    """

    def test_the_shared_root_rule_sees_one_when_there_is_one(self) -> None:
        """A source naming a shared temporary root is detected."""
        source = "'''Doc.\n\n>>> render(runner_temp=Path(\"/tmp\"))\n'''\n"

        named = shared_roots_named_in_source(source)

        assert named == ["/tmp"], named

    def test_a_commented_example_is_not_counted(self) -> None:
        """`doctest` never runs a commented line, so nor does the rule.

        The other half of the rule: it must not fire on text that
        cannot execute, or it would force changes to examples that were
        never going to write anything.
        """
        source = "'''Doc.\n\n>>> # render(runner_temp=Path(\"/tmp\"))\n'''\n"

        assert absolute_literals_in_source(source) == []

    def test_a_named_directory_that_gains_a_child_is_seen(self, tmp_path: Path) -> None:
        """A write beneath a watched directory changes its signature.

        This is the hole the review found: a file created at a path
        derived beneath a directory an example named, rather than at the
        name itself. Comparing the directory by existence missed it.
        """
        watched = tmp_path / "output"
        watched.mkdir()
        before = signature_of(watched)

        (watched / "derived").mkdir()
        (watched / "derived" / "written.json").write_text("{}", encoding="utf-8")

        assert signature_of(watched) != before, (
            "a file written beneath a watched directory left its signature "
            "unchanged, so the host-write check would not see it"
        )

    def test_a_rewritten_child_is_seen(self, tmp_path: Path) -> None:
        """Overwriting a file that was already there changes the signature.

        The second hole of the same kind, and the likelier one on a
        machine that has run this suite before: the path exists from the
        last run, the example rewrites it, and nothing is added or
        removed. A signature built from descendant names alone is
        identical across that, so the gate reported a clean run while
        the file on the host had just been replaced.
        """
        watched = tmp_path / "output"
        watched.mkdir()
        child = watched / "already-there.json"
        child.write_text("{}", encoding="utf-8")
        before = signature_of(watched)

        child.write_text('{"rewritten": true}', encoding="utf-8")

        assert signature_of(watched) != before, (
            "an example rewrote a file that already existed and the "
            "directory's signature did not change"
        )

    def test_an_unreadable_path_is_not_reported_as_absent(
        self, tmp_path: Path
    ) -> None:
        """Only a missing path is absent; anything else is a test error.

        Catching every `OSError` and answering None made the two states
        one. A path this gate cannot read reports as missing before the
        run and missing after it, so the comparison holds and a write
        between them is invisible. That is worse than a failure: the
        gate says the host was untouched precisely when it cannot tell.

        Driven with a directory whose child cannot be stat'ed because
        the parent is not searchable, which is a `PermissionError`
        rather than a `FileNotFoundError`.

        The skip is decided from the process identity before the call,
        not from whether the call raised. Deciding it afterwards made
        the test skip rather than fail when the handler was widened
        back to every `OSError`, which is a test that cannot discover
        the defect it was written for.
        """
        if getattr(os, "geteuid", lambda: 1)() == 0:
            pytest.skip("root ignores the mode, so there is no unreadable case")

        parent = tmp_path / "unsearchable"
        parent.mkdir()
        (parent / "child.txt").write_text("x", encoding="utf-8")
        parent.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                signature_of(parent / "child.txt")
        finally:
            parent.chmod(0o700)

    def test_a_shared_directory_is_not_watched_that_way(self) -> None:
        """A shared root is compared by existence, deliberately.

        Its contents move for reasons unrelated to this run, so watching
        them would make the gate fail on another process's file. The
        compensating control is that an example may not name one at all.
        """
        assert signature_of(Path(tempfile.gettempdir())) == "a shared directory"

    def test_the_examples_are_imported_inside_the_scratch_directory(
        self, tmp_path: Path
    ) -> None:
        """A module that writes at import time writes into the scratch.

        The walk derives names from files and does not pre-import them,
        so `run_examples` performs the first import for most modules,
        and a module-level statement runs then rather than inside any
        example. Importing before entering the boundary put that write
        in the repository.
        """
        witness = "written-while-importing"
        module = tmp_path / "writes_on_import.py"
        module.write_text(
            '"""A module that writes as it is imported."""\n\n'
            "from pathlib import Path\n\n"
            f'Path("{witness}").write_text("x", encoding="utf-8")\n',
            encoding="utf-8",
        )
        for landing in (REPOSITORY_ROOT / witness, tmp_path / witness):
            landing.unlink(missing_ok=True)
        sys.path.insert(0, str(tmp_path))
        try:
            outcome = run_examples("writes_on_import")
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("writes_on_import", None)

        assert outcome.verdict is not Verdict.NOT_IMPORTABLE, outcome.detail
        assert not (REPOSITORY_ROOT / witness).exists(), (
            "the module was imported in the repository root"
        )
        assert not (tmp_path / witness).exists(), (
            "the module was imported in its own directory"
        )
