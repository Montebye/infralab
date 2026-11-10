#!/usr/bin/python3 -I
"""Verify an administrator-supplied artifact before extracting or executing it."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

CLIENT_FILES = {
    "__init__.py",
    "cli.py",
    "apply.py",
    "client_journal.py",
    "manifests.py",
    "models.py",
    "validation.py",
}


def archive_check(path: Path, digest: str) -> None:
    actual = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            actual.update(chunk)
    if actual.hexdigest() != digest:
        raise ValueError(f"deployment release {path.name}: SHA256 mismatch")
    allowed = {
        "infralab_selfservice",
        "labctl_client",
        "deployment",
        "vms",
        "requirements.lock",
        "requirements-client.lock",
        "release-manifest.json",
    }
    with tarfile.open(path) as archive:
        seen: set[str] = set()
        hashes: dict[str, str] = {}
        manifest_data = b""
        for member in archive:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not name.parts
                or str(name) != member.name
                or name.parts[0] not in allowed
                or member.name in seen
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"deployment release: unsafe archive member {member.name!r}")
            seen.add(member.name)
            if not member.isfile():
                continue
            if name.parts[0] == "labctl_client" and (
                len(name.parts) != 2 or name.parts[1] not in CLIENT_FILES
            ):
                raise ValueError(f"deployment release: non-public client member {member.name!r}")
            archive_stream = archive.extractfile(member)
            if archive_stream is None:
                raise ValueError(f"deployment release: unreadable member {member.name!r}")
            if member.name == "release-manifest.json":
                if member.size > 65536:
                    raise ValueError("deployment release: oversized manifest")
                manifest_data = archive_stream.read()
            else:
                content = hashlib.sha256()
                for chunk in iter(lambda: archive_stream.read(1048576), b""):
                    content.update(chunk)
                hashes[member.name] = content.hexdigest()
        try:
            manifest: object = json.loads(manifest_data)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("deployment release: missing or invalid manifest") from exc
        compatibility = {
            "format_version": 1,
            "service_version": "0.1.0",
            "protocol_version": 1,
            "registry_schema": 3,
            "collection_version": "0.1.0",
            "installer_contract": 1,
        }
        if not isinstance(manifest, dict) or set(manifest) != set(compatibility) | {
            "files",
            "managed_vms_sha256",
        }:
            raise ValueError("deployment release: invalid manifest fields")
        for key, expected in compatibility.items():
            if type(manifest[key]) is not type(expected) or manifest[key] != expected:
                raise ValueError(f"deployment release: incompatible {key}: {manifest[key]!r}")
        if manifest["files"] != hashes:
            raise ValueError("deployment release: file inventory or content digest mismatch")
        vms = {name: digest for name, digest in hashes.items() if name.startswith("vms/")}
        managed_digest = hashlib.sha256(
            json.dumps(vms, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if not vms or manifest["managed_vms_sha256"] != managed_digest:
            raise ValueError("deployment release: managed vms content digest mismatch")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise ValueError("verify release: expected ARCHIVE SHA256")
    archive_check(Path(sys.argv[1]), sys.argv[2])
