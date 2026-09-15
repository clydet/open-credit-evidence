# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Pack loader with fingerprint verification.

Loads items.jsonl from a pack directory, verifies the manifest checksum,
and refuses to run if the pack has been tampered with.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence.contracts.item import BenchmarkItem


class TamperError(Exception):
    """Raised when pack tampering is detected."""

    def __init__(self, pack_id: str, expected: str, actual: str):
        self.pack_id = pack_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Tamper detected in pack {pack_id}: "
            f"expected items_sha256 {expected[:16]}..., got {actual[:16]}..."
        )


class PackLoadError(Exception):
    """Raised when pack loading fails."""

    pass


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class PackManifest:
    """The manifest.json from a pack."""

    pack_id: str
    version: str
    domain: str
    items: int
    cases: int
    items_sha256: str
    raw: dict[str, Any]

    @classmethod
    def from_path(cls, path: Path) -> PackManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            pack_id=data["pack_id"],
            version=data["version"],
            domain=data["domain"],
            items=data["items"],
            cases=data["cases"],
            items_sha256=data["items_sha256"],
            raw=data,
        )


@dataclass
class Pack:
    """A loaded and verified pack."""

    manifest: PackManifest
    items: list[BenchmarkItem]
    path: Path

    def items_by_id(self) -> dict[str, BenchmarkItem]:
        return {item.item_id: item for item in self.items}


class PackLoader:
    """Loads packs with tamper verification."""

    def __init__(self, verify: bool = True):
        self.verify = verify

    def load(self, pack_path: Path | str) -> Pack:
        """Load a pack from disk, optionally verifying integrity."""
        pack_dir = Path(pack_path)

        if not pack_dir.is_dir():
            raise PackLoadError(f"Pack directory not found: {pack_dir}")

        manifest_path = pack_dir / "manifest.json"
        items_path = pack_dir / "items.jsonl"

        if not manifest_path.exists():
            raise PackLoadError(f"manifest.json not found in {pack_dir}")
        if not items_path.exists():
            raise PackLoadError(f"items.jsonl not found in {pack_dir}")

        manifest = PackManifest.from_path(manifest_path)

        if self.verify:
            actual_sha = compute_file_sha256(items_path)
            if actual_sha != manifest.items_sha256:
                raise TamperError(manifest.pack_id, manifest.items_sha256, actual_sha)

        items: list[BenchmarkItem] = []
        with items_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(BenchmarkItem.model_validate_json(line))

        if len(items) != manifest.items:
            raise PackLoadError(
                f"Item count mismatch: manifest says {manifest.items}, "
                f"found {len(items)}"
            )

        return Pack(manifest=manifest, items=items, path=pack_dir)


def load_answer_key(pack_path: Path | str) -> dict[str, Any] | None:
    """Load the sealed answer key if present. Returns None if not found."""
    key_path = Path(pack_path) / "answer_key.json"
    if not key_path.exists():
        return None
    return json.loads(key_path.read_text(encoding="utf-8"))
