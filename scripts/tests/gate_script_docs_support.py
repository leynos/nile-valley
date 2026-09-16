"""Discovery and execution for the documented-example gate.

Repository policy is that function documentation carries an example
showing usage and outcome. An example that has drifted from the code is
worse than none, so every example in every module under `scripts` is
executed by the tests that import this module.

The module list is walked rather than written down. The hand-written one
this replaces named eleven modules while thirty-four carried examples,
so 199 of 269 example lines were never run, and adding a module with a
stale example changed nothing a reader would notice.

The walk, the two exemption lists and the execution boundary live here
rather than in a test module because three test modules share them, and
a second copy of the walk is a second answer to what the gate covers.
"""

from __future__ import annotations

import contextlib
import doctest
import enum
import importlib
import os
import tempfile
import typing as typ
from collections.abc import Iterator
from pathlib import Path

#: `conftest.py` is pytest's to import. Importing it a second time under
#: a dotted name would run its `sys.path` setup again against a
#: different module object, so its own examples are left to pytest.
NOT_OURS_TO_IMPORT = frozenset({"conftest", "__init__"})

#: Directories under `scripts` this gate does not import, for the same
#: reason as `conftest`: the suite is pytest's, and a second import
#: under a dotted name re-runs every module-level statement against a
#: different module object. It is also not merely untidy. The spelling
#: gate runs a narrower pytest invocation that omits `cmd-mox` on
#: purpose, and three modules here import it at module level, so under
#: that invocation the second import raises and this gate reports a
#: missing package as a stale example.
#:
#: Their own examples are not abandoned: executing them is
#: `--doctest-modules` on the suite's own invocation, which is where a
#: module pytest already imports belongs.
NOT_OURS_TO_WALK = frozenset({"tests"})

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent


def _module_names() -> tuple[str, ...]:
    """Return every module under `scripts`, in a stable order.

    Enumerated rather than listed by hand. The list this replaces named
    eleven modules while thirty-four carried examples, and nothing said
    so: adding a module with a stale example left it unchecked, and the
    suite stayed green. A list that cannot be added to cannot drift.

    Returns
    -------
    tuple[str, ...]
        Importable dotted names, sorted so the parametrisation ids are
        stable between runs.
    """
    names = [
        ".".join(path.relative_to(REPOSITORY_ROOT).with_suffix("").parts)
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if path.stem not in NOT_OURS_TO_IMPORT
        and NOT_OURS_TO_WALK.isdisjoint(path.relative_to(PACKAGE_ROOT).parts[:-1])
    ]
    assert names, f"no modules found under {PACKAGE_ROOT}; the walk is wrong"
    return tuple(names)


GATE_MODULES = _module_names()

#: Modules whose examples did not hold when the walk replaced the hand
#: list, on 2026-09-15. Eleven modules, down from seventeen: the
#: manifest writer's examples named absolute paths under `/tmp` and
#: wrote to them, so running them at all was the defect and repairing
#: them retired its entry the same day. The platform renderer went the
#: same way: its examples called out to OpenTofu and wrote a variables
#: file under the temporary directory they named, behind a comment
#: saying they were illustrative, which `doctest` does not read. They
#: are marked as skipped now, which is a thing it does read, and they
#: hold. The input preparer went with them: its two examples were
#: repaired to make their own temporary directory, and once they ran at
#: all the only thing still wrong was that they did not state the
#: secret masking the call prints. The rest mostly name functions
#: that have since been renamed or removed. Repairing those is not this
#: branch's work, and turning the gate red on it would be worse than
#: recording it.
#:
#: This list only ever shrinks. `test_a_listed_module_is_still_stale`
#: fails when a listed module starts passing, so a repair cannot leave
#: its entry behind, and nothing adds to the list by accident: a module
#: not named here is checked from the moment it exists. Tracked in
#: leynos/nile-valley#103.
KNOWN_STALE_EXAMPLES = frozenset(
    {
        "scripts._gitops_repo",
        "scripts._infra_k8s_errors",
        "scripts._infra_k8s_github",
        "scripts._infra_k8s_tofu",
        "scripts._prepare_infra_k8s_models",
        "scripts._provision_cluster_flow",
        "scripts._render_platform_inputs",
        "scripts._vault_bootstrap",
        "scripts._vault_commands",
        "scripts.check_test_dependencies",
        "scripts.publish_infra_k8s_outputs",
    }
)

#: Modules this gate cannot import, for a reason that is not a stale
#: example and does not belong beside one. Each imports a sibling by
#: bare name, which resolves only when `scripts` is itself on the path.
#: The spelling gate runs that way and they work there; under this
#: suite's layout they are `scripts.<name>` and the bare import misses.
#:
#: Recorded separately because the distinction is the point. Collapsing
#: an import failure into "stale examples" is what let an exemption for
#: a deleted module satisfy the shrink-only rule forever, and it would
#: equally hide three modules whose examples have never run at all.
#: Adding `scripts` to `sys.path` here would import each of them twice
#: under two names, which is the fault this gate was just scoped to
#: avoid, so the fix belongs in the modules. Tracked with the stale
#: examples in leynos/nile-valley#103.
NOT_IMPORTABLE_HERE = frozenset(
    {
        "scripts.generate_typos_config",
        "scripts.typos_rollout",
        "scripts.typos_rollout_http",
    }
)

CHECKED_MODULES = tuple(
    m
    for m in GATE_MODULES
    if m not in KNOWN_STALE_EXAMPLES and m not in NOT_IMPORTABLE_HERE
)


class Verdict(enum.StrEnum):
    """How a module's examples came out.

    Three things go wrong here and only one of them is a wrong expected
    value. Collapsing them into "a reason" made the exemption test
    unfalsifiable: a module that had been deleted failed to import, an
    import failure read as a reason, and a reason was all the test
    asked for. They are separate states now because the test has to
    tell them apart.
    """

    HELD = "held"
    NOT_IMPORTABLE = "not-importable"
    STALE = "stale"


class Outcome(typ.NamedTuple):
    """What running one module's examples produced.

    Attributes
    ----------
    verdict:
        Which of the three states it reached.
    detail:
        A short human-readable account, for the assertion message.
    """

    verdict: Verdict
    detail: str

    @property
    def held(self) -> bool:
        """Whether every example held."""
        return self.verdict is Verdict.HELD


@contextlib.contextmanager
def in_a_scratch_directory() -> Iterator[Path]:
    """Run the body with the process rooted in a fresh temporary directory.

    Documented examples are ordinary code and some of them write. Two
    in the manifest writer named absolute paths under `/tmp` and
    created them on every run of this suite, on a machine the gate
    shares with everything else. Those two are repaired at the source,
    but a gate that walks every module cannot assume the next one added
    will be careful, so the execution happens somewhere disposable and
    the process is put back afterwards.

    Yields
    ------
    Path
        The scratch directory, already the working directory.
    """
    origin = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="doctest-gate-") as directory:
        scratch = Path(directory)
        os.chdir(scratch)
        try:
            yield scratch
        finally:
            os.chdir(origin)


def run_examples(module_name: str) -> Outcome:
    """Import a module and run its documented examples, in isolation.

    The explicit boundary. This is the only function here that imports
    anything, executes anything or touches a filesystem, and it does
    the last of those from a scratch directory it throws away. Its
    callers read an `Outcome` and decide; they cause nothing.

    Parameters
    ----------
    module_name : str
        The dotted module name.

    Returns
    -------
    Outcome
        The verdict and a short account of it.
    """
    # The import is inside the boundary, not before it. A first import
    # runs the module's top-level statements, and a module that writes
    # at import time would otherwise do so in the repository: the walk
    # derives names from files and does not pre-import them, so for most
    # of these this call is the first import there has been.
    with in_a_scratch_directory():
        try:
            module = importlib.import_module(module_name)
        except Exception as error:  # noqa: BLE001 - the reason is the answer
            return Outcome(Verdict.NOT_IMPORTABLE, f"{type(error).__name__}: {error}")
        try:
            results = doctest.testmod(
                module, verbose=False, optionflags=doctest.NORMALIZE_WHITESPACE
            )
        except Exception as error:  # noqa: BLE001 - a malformed docstring lands here
            return Outcome(Verdict.STALE, f"{type(error).__name__}: {error}")
    if results.failed:
        return Outcome(
            Verdict.STALE, f"{results.failed} of {results.attempted} example(s) stale"
        )
    return Outcome(Verdict.HELD, f"{results.attempted} example(s) held")
