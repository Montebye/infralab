#!/usr/bin/python3 -I
"""Verify an administrator-supplied release archive before extracting or executing it.

Checks the SHA256 the administrator pinned and the generic rules of release format 2 and
installer contract 2. The payload itself (file names, counts, versions) is not known here.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
import tarfile
import zlib
from pathlib import Path, PurePosixPath
from typing import IO

FORMAT_VERSION = 2
INSTALLER_CONTRACT = 2
MANIFEST = "release-manifest.json"
INSTALLER = "installer/install.py"
TOP_LEVEL = {MANIFEST, "installer", "root"}
MAX_MEMBERS = 10000
MAX_MANIFEST_BYTES = 1048576
TREES = ("/opt/infralab-selfservice", "/opt/infralab-labctl")
DESTINATION_PREFIXES = (
    *(f"{tree}/" for tree in TREES),
    "/usr/local/bin/",
    "/usr/local/sbin/",
    "/usr/local/libexec/infralab-selfservice/",
    "/usr/share/polkit-1/actions/",
    "/etc/systemd/system/infralab-selfservice",
)
SHA256 = re.compile(r"[0-9a-f]{64}")
MODE = re.compile(r"0[0-7]{3}")


def _digest(stream: IO[bytes]) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(1048576)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"deployment release: manifest repeats key {key!r}")
        document[key] = value
    return document


def _constant(value: str) -> object:
    raise ValueError(f"deployment release: manifest contains the non-finite number {value}")


def _members(path: Path) -> tuple[bytes | None, str | None, dict[str, str]]:
    """(manifest bytes, installer digest, destination -> digest of every root/ file)."""
    manifest: bytes | None = None
    installer: str | None = None
    contents: dict[str, str] = {}
    seen: set[str] = set()
    with tarfile.open(path, "r:gz") as archive:
        for count, member in enumerate(archive, start=1):
            if count > MAX_MEMBERS:
                raise ValueError(f"deployment release: more than {MAX_MEMBERS} archive members")
            name = PurePosixPath(member.name)
            # An absolute name starts with "/", which the top-level check refuses.
            if (
                ".." in name.parts
                or not name.parts
                or str(name) != member.name
                or name.parts[0] not in TOP_LEVEL
                or member.name in seen
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"deployment release: unsafe archive member {member.name!r}")
            seen.add(member.name)
            if member.isdir() and member.name != MANIFEST:
                continue
            stream = archive.extractfile(member) if member.isfile() else None
            if member.name == MANIFEST and stream is not None:
                if member.size > MAX_MANIFEST_BYTES:
                    raise ValueError(
                        f"deployment release: manifest exceeds {MAX_MANIFEST_BYTES} bytes"
                    )
                manifest = stream.read()
            elif member.name == INSTALLER and stream is not None:
                installer = _digest(stream)
            elif name.parts[0] == "root" and len(name.parts) > 1 and stream is not None:
                contents["/" + "/".join(name.parts[1:])] = _digest(stream)
            else:
                raise ValueError(f"deployment release: unexpected archive member {member.name!r}")
        # tarfile stops silently at the first block it cannot parse, where GNU tar skips ahead and
        # extracts more: only zero blocks may follow, up to the clean end of the gzip stream.
        rest = archive.fileobj
        if rest is None:
            raise ValueError("deployment release: archive stream unavailable")
        rest.seek(archive.offset)
        while True:
            chunk = rest.read(1048576)
            if not chunk:
                break
            if chunk.count(0) != len(chunk):
                raise ValueError(
                    f"deployment release: data after the end of the archive at offset "
                    f"{archive.offset}"
                )
    return manifest, installer, contents


def _manifest(data: bytes) -> dict[str, object]:
    try:
        document: object = json.loads(
            data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("deployment release: missing or invalid manifest") from exc
    if not isinstance(document, dict):
        raise ValueError("deployment release: manifest is not a JSON object")
    return {str(key): value for key, value in document.items()}


def _files(value: object) -> dict[str, str]:
    """Destination -> sha256 of the manifest's file entries."""
    if not isinstance(value, dict):
        raise ValueError("deployment release: manifest files is not a JSON object")
    files: dict[str, str] = {}
    for destination, entry in value.items():
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        mode = entry.get("mode") if isinstance(entry, dict) else None
        if (
            not isinstance(digest, str)
            or SHA256.fullmatch(digest) is None
            or not isinstance(mode, str)
            or MODE.fullmatch(mode) is None
        ):
            raise ValueError(f"deployment release: invalid manifest entry {destination!r}")
        parts = str(destination).split("/")
        if parts[0] or any(part in ("", ".", "..") for part in parts[1:]):
            raise ValueError(
                f"deployment release: destination {destination!r} is not a normalised absolute path"
            )
        if not str(destination).startswith(DESTINATION_PREFIXES):
            raise ValueError(
                f"deployment release: destination {destination!r} is outside the allowed prefixes"
            )
        files[str(destination)] = digest
    return files


def archive_check(path: Path, digest: str) -> None:
    if SHA256.fullmatch(digest) is None:
        raise ValueError("deployment release: expected SHA256 is not 64 lowercase hexadecimal")
    with path.open("rb") as stream:
        if _digest(stream) != digest:
            raise ValueError(f"deployment release {path.name}: SHA256 mismatch")
    try:
        manifest_data, installer, contents = _members(path)
    except (tarfile.TarError, EOFError, zlib.error, gzip.BadGzipFile) as exc:
        raise ValueError(f"deployment release {path.name}: unreadable archive: {exc}") from exc
    if manifest_data is None:
        raise ValueError("deployment release: missing or invalid manifest")
    manifest = _manifest(manifest_data)
    for key, expected in (
        ("format_version", FORMAT_VERSION),
        ("installer_contract", INSTALLER_CONTRACT),
    ):
        value = manifest.get(key)
        if type(value) is not int or value != expected:
            raise ValueError(f"deployment release: incompatible {key}: {value!r}")
    if installer is None:
        raise ValueError(f"deployment release: installer member {INSTALLER!r} is missing")
    if manifest.get("installer_sha256") != installer:
        raise ValueError(f"deployment release: member {INSTALLER!r} differs from installer_sha256")
    trees = manifest.get("trees")
    if not isinstance(trees, dict):
        raise ValueError("deployment release: manifest trees is not a JSON object")
    if set(trees) != set(TREES):
        raise ValueError(
            f"deployment release: manifest trees {sorted(trees)!r} differ from {list(TREES)!r}"
        )
    for tree, mode in sorted(trees.items()):
        if not isinstance(mode, str) or MODE.fullmatch(mode) is None:
            raise ValueError(f"deployment release: tree {tree!r} has the invalid mode {mode!r}")
    files = _files(manifest.get("files"))
    unlisted = sorted(set(contents) - set(files))
    if unlisted:
        raise ValueError(
            f"deployment release: member 'root{unlisted[0]}' is not listed in the manifest"
        )
    absent = sorted(set(files) - set(contents))
    if absent:
        raise ValueError(f"deployment release: manifest entry {absent[0]!r} has no member")
    for destination, listed in sorted(files.items()):
        if contents[destination] != listed:
            raise ValueError(
                f"deployment release: content digest mismatch for member 'root{destination}'"
            )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise ValueError("verify release: expected ARCHIVE SHA256")
    archive_check(Path(sys.argv[1]), sys.argv[2])
