"""Drive the strict workflow loader over constructed directories.

The repository's own workflows are all lower-case `.yml` mappings with no
repeated keys, so contracts that read them pass whether or not the loader
handles any other case. These tests build the other cases.

Run via ``make test``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from workflow_loader import (
    DuplicateKeyError,
    WorkflowReadError,
    load_workflow,
    read_workflows,
)


def test_suffixes_match_case_insensitively_in_file_name_order(
    tmp_path: Path,
) -> None:
    """Every spelling of both extensions is read, in file-name order.

    GitHub runs `CI.YML` as readily as `ci.yml`. A non-workflow file and a
    directory whose name ends in `.yml` are skipped. The order is asserted
    as returned, not after sorting, because callers rely on it.
    """
    for name in ("b.yml", "A.YAML", "c.Yml", "notes.txt"):
        (tmp_path / name).write_text("on: push\n", encoding="utf-8")
    (tmp_path / "nested.yml").mkdir()
    names = list(read_workflows(tmp_path))
    assert names == ["A.YAML", "b.yml", "c.Yml"], (
        f"read_workflows returned {names} for mixed-case suffixes"
    )


@pytest.mark.parametrize("text", ["just a scalar\n", "", "~\n", "- a\n- b\n"])
def test_a_document_that_is_not_a_mapping_reads_as_empty(text: str) -> None:
    """A scalar, empty, null or list document parses to an empty mapping."""
    document = load_workflow(text)
    assert document == {}, f"load_workflow({text!r}) returned {document!r}"


def test_a_nested_duplicate_key_is_refused() -> None:
    """A key repeated inside a job, not only at the top, is refused."""
    text = "jobs:\n  build:\n    runs-on: a\n    runs-on: b\n"
    with pytest.raises(DuplicateKeyError, match="found duplicate key 'runs-on'"):
        load_workflow(text)


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"on: [push\n", "malformed YAML"),
        (b"on: push\non: pull_request\n", "duplicate key"),
        (b"name: \xff\xfe\n", "invalid UTF-8"),
    ],
    ids=["malformed", "duplicate-key", "invalid-utf8"],
)
def test_an_unreadable_workflow_is_reported_with_its_path(
    tmp_path: Path, content: bytes, reason: str
) -> None:
    """Each read failure arrives as `WorkflowReadError` naming the file."""
    path = tmp_path / "broken.yml"
    path.write_bytes(content)
    with pytest.raises(WorkflowReadError, match="broken.yml") as caught:
        read_workflows(tmp_path)
    assert caught.value.__cause__ is not None, (
        f"a {reason} failure must keep its original cause"
    )


def test_a_missing_directory_is_reported_rather_than_read_as_empty(
    tmp_path: Path,
) -> None:
    """An absent directory raises instead of yielding no workflows.

    An empty result would let every contract above it pass having read
    nothing.
    """
    missing = tmp_path / "absent"
    with pytest.raises(WorkflowReadError, match="absent"):
        read_workflows(missing)
