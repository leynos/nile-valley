"""Contract tests for the repository's CodeScene rule overrides.

`.codescene/code-health-rules.json` sat here in a shape CodeScene does not
accept, so the exemption it declared never applied. Nothing caught it: the
file is valid JSON, the tool's own diagnostic blames JSON syntax, and the
warning goes to a log nobody reads. CodeScene's verdicts simply carried on
without the override.

The rule set was dead as well as unreadable. Its glob was `**/domain/*.rs`
and this repository contains no Rust, so it was removed rather than repaired.
These tests guard the file a future exemption would be written into: they
assert the documented schema rather than merely that the file parses, require
each exemption to justify itself, and require each glob to still match
something, because a glob left behind by a rename or a copy is an exemption
that quietly stops applying.

`cs rules-config validate` is the local check the developers' guide points at.
The command-line tool does not belong in CI, because the GitHub integration
reads the same rule set; these tests are a schema check rather than a stand-in
for either.
"""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPOSITORY_ROOT / ".codescene" / "code-health-rules.json"

#: Keys `cs docs code-health-rules-template` emits for a rule set. `usage` and
#: the `_doc` suffixes are documentation the template carries itself, so they
#: are allowed rather than required.
RULE_SET_KEYS = frozenset(
    {
        "matching_content_path",
        "matching_content_path_doc",
        "content_filter",
        "rules",
        "thresholds",
    }
)

MINIMUM_JUSTIFICATION = 80


def _rule_sets() -> list[dict[str, typ.Any]]:
    """Return the file's rule sets, failing if the top-level shape is wrong."""
    document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "the rule file must be a JSON object"
    rule_sets = document.get("rule_sets")
    assert isinstance(rule_sets, list), (
        "the rule file must carry a top-level 'rule_sets' array; a top-level "
        "'rules' object is the shape CodeScene rejects, and it rejects it "
        "with a message about JSON syntax that sends the reader elsewhere"
    )
    assert rule_sets, "an empty rule_sets array declares no override at all"
    return typ.cast("list[dict[str, typ.Any]]", rule_sets)


def _check_rule(rule: dict[str, typ.Any]) -> None:
    """Assert one rule override carries a prose name and a weight."""
    assert set(rule) == {"name", "weight"}, (
        f"a rule override carries exactly a name and a weight: {rule}"
    )
    assert isinstance(rule["name"], str) and " " in rule["name"], (
        "rules are named in prose, as in 'String Heavy Function Arguments', "
        f"not as a hyphenated slug: {rule['name']!r}"
    )
    weight = rule["weight"]
    assert isinstance(weight, int | float) and 0.0 <= weight <= 1.0, (
        "a rule's weight is a relative multiplier between 0.0 and 1.0, not a "
        f"threshold: {weight!r}"
    )


def check_schema() -> None:
    """Assert the rule file uses the keys CodeScene reads.

    Asserting the key names matters more than it looks. The shape this
    replaces used hyphenated keys, which CodeScene's parser reads as
    namespaced keywords and refuses, so a typo here fails the same way:
    silently, with the override ignored.
    """
    for rule_set in _rule_sets():
        assert isinstance(rule_set, dict), "each rule set must be an object"
        unexpected = set(rule_set) - RULE_SET_KEYS
        assert not unexpected, (
            f"unrecognized rule set keys {sorted(unexpected)}; CodeScene "
            "ignores what it does not recognize"
        )
        for rule in rule_set.get("rules", []):
            _check_rule(rule)


def check_justifications() -> None:
    """Assert each rule set explains itself, so a reader can judge it.

    An exemption without a stated reason is indistinguishable from one nobody
    revisited, which is how a narrow allowance becomes a permanent blind spot.
    """
    for rule_set in _rule_sets():
        justification = rule_set.get("matching_content_path_doc", "")
        assert len(justification) > MINIMUM_JUSTIFICATION, (
            "each rule set needs a matching_content_path_doc saying why the "
            f"exemption is deliberate: {rule_set.get('matching_content_path')!r}"
        )


def check_globs_match() -> None:
    """Assert each rule set's glob matches at least one file.

    A path left behind by a rename, or copied from another repository, leaves
    an exemption that quietly stops applying. That was half of this file's
    defect: its glob named Rust sources in a repository that has none.
    """
    for rule_set in _rule_sets():
        pattern = rule_set.get("matching_content_path")
        assert isinstance(pattern, str) and pattern, (
            "each rule set must declare a matching_content_path"
        )
        matched = next(REPOSITORY_ROOT.glob(pattern), None)
        assert matched is not None, (
            f"no file matches {pattern!r}; an exemption that matches nothing "
            "is either stale or was never right"
        )


CHECKS = (check_schema, check_justifications, check_globs_match)


def test_the_repository_declares_no_codescene_overrides() -> None:
    """There is no rule file, because the only rule set was dead.

    Removing it changed no verdict: CodeScene never read the file. This test
    states the current position, so re-adding a rule file is a deliberate act
    that arrives with the checks below.
    """
    assert not RULES_PATH.exists(), (
        f"{RULES_PATH.name} is back; delete this test and let the checks below "
        "run against it, having validated it with `cs rules-config validate`"
    )


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.__name__)
def test_a_rule_file_would_have_to_pass_each_check(
    check: typ.Callable[[], None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A well-formed rule file satisfies every check.

    The file is written here rather than committed, so the checks stay
    exercised while the repository declares no overrides.
    """
    document = {
        "usage": "Repo-scoped CodeScene overrides.",
        "rule_sets": [
            {
                "matching_content_path": "scripts/*.py",
                "matching_content_path_doc": (
                    "A justification long enough to say why the exemption is "
                    "deliberate, what it covers, and when to reassess it."
                ),
                "rules": [{"name": "String Heavy Function Arguments", "weight": 0.0}],
            }
        ],
    }
    path = tmp_path / "code-health-rules.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    # `raising` is left at its default on purpose: if this module is ever
    # imported under a different name the patch must fail loudly rather than
    # create a new attribute and let the test pass having patched nothing.
    monkeypatch.setattr(f"{__name__}.RULES_PATH", path)

    check()


@pytest.mark.parametrize(
    ("document", "failing_checks"),
    [
        pytest.param(
            {
                "rules": {
                    "string-heavy-function-arguments": {
                        "threshold-by-pattern": {"**/domain/*.rs": 100}
                    }
                }
            },
            CHECKS,
            id="the-file-this-replaces",
        ),
        pytest.param(
            {"rule_sets": [{"rules": [{"name": "String Heavy", "weight": 100}]}]},
            CHECKS,
            id="a-threshold-where-a-weight-belongs",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [
                            {"name": "string-heavy-arguments", "weight": 0.0}
                        ],
                    }
                ]
            },
            (check_schema,),
            id="a-slug-where-a-prose-name-belongs",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "**/domain/*.rs",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [
                            {"name": "String Heavy Arguments", "weight": 0.0}
                        ],
                    }
                ]
            },
            (check_globs_match,),
            id="a-glob-matching-nothing",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "rules": [
                            {"name": "String Heavy Arguments", "weight": 0.0}
                        ],
                    }
                ]
            },
            (check_justifications,),
            id="an-unjustified-exemption",
        ),
    ],
)
def test_the_checks_reject_known_bad_shapes(
    document: dict[str, typ.Any],
    failing_checks: tuple[typ.Callable[[], None], ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each check must fail on the shapes that caused this.

    Without this the checks could assert nothing and still pass, which is the
    defect they exist to catch, one level up.
    """
    path = tmp_path / "code-health-rules.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.RULES_PATH", path)

    for check in failing_checks:
        with pytest.raises(AssertionError):
            check()
