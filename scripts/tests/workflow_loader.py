"""Strict loading for every workflow contract in this directory.

The pull-request cancel contract loads the tree through here, and any other
contract that moves here shares the same refusal. PyYAML's ``safe_load`` keeps the last value of a duplicated
mapping key and says nothing, so a lane declaring ``runs-on`` twice parses
into a document that has silently discarded half of what GitHub was asked to
run; the loader here refuses the document instead. It also reads both
spellings of the extension, compared case-insensitively, because GitHub runs
``CI.YML`` as readily as ``ci.yml``.

Use ``read_workflows`` for a directory, passing ``WORKFLOW_DIR`` for this
repository's tree, and ``load_workflow`` for one document. Parse
workflow files through nothing else in this directory.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import yaml

#: Both spellings GitHub accepts for a workflow file's extension, compared
#: lowercased so that ``CI.YML`` is not skipped in silence.
WORKFLOW_SUFFIXES: typ.Final = frozenset({".yml", ".yaml"})

#: This repository's workflow directory.
WORKFLOW_DIR: typ.Final = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows"
)

Document = dict[object, object]


class DuplicateKeyError(yaml.constructor.ConstructorError):
    """A mapping declared the same key twice."""


class WorkflowReadError(OSError):
    """A workflow directory or file could not be read or parsed.

    Reading fails in ways that look nothing alike to a caller: a missing
    directory, an unreadable file, bytes that are not UTF-8, text that is not
    YAML, or a repeated key. Each arrives here carrying the path, so a
    contract can report which workflow broke instead of a bare decode error.
    """


class StrictLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that refuses duplicate mapping keys.

    Examples
    --------
    >>> yaml.load("a: 1\\nb: 2\\n", Loader=StrictLoader)
    {'a': 1, 'b': 2}
    """

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        """Build a mapping, refusing a key that appears twice."""
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise DuplicateKeyError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_workflow(text: str) -> Document:
    """Parse one workflow strictly.

    Parameters
    ----------
    text
        The workflow's YAML source.

    Returns
    -------
    Document
        The parsed document, or an empty mapping when the source holds no
        mapping at all.

    Raises
    ------
    DuplicateKeyError
        When any mapping in the document declares a key twice.

    Examples
    --------
    >>> load_workflow("on: push\\njobs: {}\\n")
    {True: 'push', 'jobs': {}}
    """
    document = yaml.load(text, Loader=StrictLoader)
    return document if isinstance(document, dict) else {}


def read_workflows(directory: Path) -> dict[str, Document]:
    """Parse every workflow in a directory, keyed by file name.

    Parameters
    ----------
    directory
        The directory holding the workflow files, usually ``WORKFLOW_DIR``.

    Returns
    -------
    dict[str, Document]
        Each regular ``.yml`` or ``.yaml`` file's parsed document, keyed by
        file name and inserted in file-name order; the extension is matched
        case-insensitively, and a document that is not a mapping reads as
        an empty one.

    Raises
    ------
    WorkflowReadError
        When the directory cannot be listed, or a workflow cannot be read,
        is not UTF-8, is not YAML, or declares a mapping key twice. The
        message names the path.
    """
    try:
        entries = sorted(directory.iterdir())
    except OSError as error:
        message = f"{directory} could not be listed: {error}"
        raise WorkflowReadError(message) from error
    paths = [
        path
        for path in entries
        if path.is_file() and path.suffix.lower() in WORKFLOW_SUFFIXES
    ]
    return {path.name: _read_one(path) for path in paths}


def _read_one(path: Path) -> Document:
    """Read and parse one workflow file, naming it in any failure."""
    try:
        return load_workflow(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        message = f"{path} could not be read as a workflow: {error}"
        raise WorkflowReadError(message) from error
