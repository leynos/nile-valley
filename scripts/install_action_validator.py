#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["plumbum"]
# ///
"""Install action-validator with checksum verification.

Examples
--------
Install the Linux amd64 release into a local bin directory:

$ uv run scripts/install_action_validator.py \
    --url https://github.com/mpalmer/action-validator/releases/download/v0.8.0/action-validator_linux_amd64 \
    --checksum-url https://api.github.com/repos/mpalmer/action-validator/releases/tags/v0.8.0 \
    --local-bin ~/.local/bin \
    --binary-name action-validator_linux_amd64
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from plumbum import local

__all__ = [
    "InstallConfig",
    "install_action_validator",
]


@dataclass(frozen=True)
class InstallConfig:
    """Configuration for installing action-validator."""

    url: str
    checksum_url: str
    local_bin: Path
    binary_name: str


class ActionValidatorInstallError(RuntimeError):
    """Raised when action-validator installation fails."""


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "nile-valley-ci"})
    try:
        with urlopen(request) as response:
            destination.write_bytes(response.read())
    except HTTPError as exc:
        raise ActionValidatorInstallError(
            f"Failed to download {url}: HTTP {exc.code}."
        ) from exc
    except URLError as exc:
        raise ActionValidatorInstallError(
            f"Failed to download {url}: {exc.reason}."
        ) from exc


def _is_hex_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        char in "0123456789abcdefABCDEF" for char in value
    )


def _parse_checksum_json(payload: dict[str, object], binary_name: str) -> str:
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise ActionValidatorInstallError("Release metadata assets are invalid.")

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") != binary_name:
            continue
        digest = asset.get("digest", "")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            return digest.split(":", 1)[1]
        break

    raise ActionValidatorInstallError(
        f"No SHA256 digest found for {binary_name}."
    )


def _parse_checksum_text(text: str, binary_name: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) == 1 and _is_hex_sha256(parts[0]):
            return parts[0]
        if len(parts) >= 2 and parts[1] in {binary_name, f"*{binary_name}"}:
            if _is_hex_sha256(parts[0]):
                return parts[0]

    raise ActionValidatorInstallError(
        f"No SHA256 checksum entry found for {binary_name}."
    )


def _read_checksum(checksum_file: Path, binary_name: str) -> str:
    content = checksum_file.read_text(encoding="utf-8").strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return _parse_checksum_text(content, binary_name)
    return _parse_checksum_json(payload, binary_name)


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 128), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_sha256(path: Path, expected: str) -> None:
    actual = _file_sha256(path)
    if actual.lower() != expected.lower():
        raise ActionValidatorInstallError(
            f"SHA256 mismatch for {path.name}: expected {expected}, got {actual}."
        )


def _install_binary(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / "action-validator"
    destination_path.write_bytes(source.read_bytes())
    destination_path.chmod(0o755)
    return destination_path


def _run_version(binary_path: Path) -> None:
    local[str(binary_path)]["--version"]()


def install_action_validator(config: InstallConfig) -> Path:
    """Download, verify, and install action-validator.

    Returns
    -------
    Path
        The installed action-validator binary path.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        binary_path = tmp_path / config.binary_name
        checksum_path = tmp_path / f"{config.binary_name}.checksum"

        _download(config.url, binary_path)
        _download(config.checksum_url, checksum_path)
        checksum_value = _read_checksum(checksum_path, config.binary_name)
        _verify_sha256(binary_path, checksum_value)
        installed_path = _install_binary(binary_path, config.local_bin)

    _run_version(installed_path)
    return installed_path


def _parse_args(argv: list[str] | None) -> InstallConfig:
    parser = argparse.ArgumentParser(
        description="Install action-validator with checksum verification."
    )
    parser.add_argument("--url", required=True, help="Download URL for the binary.")
    parser.add_argument(
        "--checksum-url",
        required=True,
        help="Download URL for the checksum metadata.",
    )
    parser.add_argument(
        "--local-bin",
        required=True,
        type=Path,
        help="Destination directory for the binary.",
    )
    parser.add_argument(
        "--binary-name",
        required=True,
        help="Asset name to locate in checksum metadata.",
    )
    args = parser.parse_args(argv)
    return InstallConfig(
        url=args.url,
        checksum_url=args.checksum_url,
        local_bin=args.local_bin,
        binary_name=args.binary_name,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the installer entrypoint."""
    config = _parse_args(argv)
    try:
        install_action_validator(config)
    except ActionValidatorInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
