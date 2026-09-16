"""The documented-example gate's write rules, driven to breaking point.

Every rule in :mod:`scripts.tests.gate_script_docs_path_support` is
parametrised elsewhere over the repository's own modules, where it
passes because the sources are correct. A rule proved only that way
survives its own mutation. These drive the mechanisms directly against
inputs written to violate them.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

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
