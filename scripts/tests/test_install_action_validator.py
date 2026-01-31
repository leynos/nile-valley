"""Tests for the action-validator installer script."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.install_action_validator import (
    ActionValidatorInstallError,
    InstallConfig,
    _read_checksum,
    _verify_sha256,
    install_action_validator,
)


def test_read_checksum_from_json(tmp_path: Path) -> None:
    binary_name = "action-validator_linux_amd64"
    expected = "a" * 64
    payload = {
        "assets": [
            {
                "name": binary_name,
                "digest": f"sha256:{expected}",
            }
        ]
    }
    checksum_file = tmp_path / "release.json"
    checksum_file.write_text(json.dumps(payload), encoding="utf-8")

    assert _read_checksum(checksum_file, binary_name) == expected


def test_read_checksum_from_text(tmp_path: Path) -> None:
    binary_name = "action-validator_linux_amd64"
    expected = "b" * 64
    checksum_file = tmp_path / "checksum.txt"
    checksum_file.write_text(
        f"{expected}  {binary_name}\n",
        encoding="utf-8",
    )

    assert _read_checksum(checksum_file, binary_name) == expected


def test_verify_sha256_mismatch(tmp_path: Path) -> None:
    binary_path = tmp_path / "binary"
    binary_path.write_bytes(b"nile-valley")

    with pytest.raises(ActionValidatorInstallError, match="SHA256 mismatch"):
        _verify_sha256(binary_path, "0" * 64)


def test_install_action_validator_with_file_urls(tmp_path: Path) -> None:
    binary_name = "action-validator_linux_amd64"
    binary_source = tmp_path / binary_name
    binary_source.write_text(
        "#!/usr/bin/env sh\nprintf 'action-validator 0.8.0\\n'\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(binary_source.read_bytes()).hexdigest()

    payload = {
        "assets": [
            {
                "name": binary_name,
                "digest": f"sha256:{digest}",
            }
        ]
    }
    checksum_source = tmp_path / "release.json"
    checksum_source.write_text(json.dumps(payload), encoding="utf-8")

    local_bin = tmp_path / "bin"
    config = InstallConfig(
        url=binary_source.as_uri(),
        checksum_url=checksum_source.as_uri(),
        local_bin=local_bin,
        binary_name=binary_name,
    )

    installed_path = install_action_validator(config)

    assert installed_path.exists()
    assert installed_path.read_text(encoding="utf-8").startswith("#!/usr/bin/env sh")
