# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Tests for pack loading and integrity verification.

Acceptance criterion E1: A one-byte edit to items.jsonl makes the loader
refuse the pack, naming the checksum mismatch.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from evidence.engine.loader import (
    PackLoader,
    PackLoadError,
    TamperError,
    compute_file_sha256,
)


def _create_test_pack(tmp: Path, *, items_content: str | None = None) -> Path:
    """Create a minimal test pack."""
    pack_dir = tmp / "test-pack"
    pack_dir.mkdir(parents=True)

    if items_content is None:
        items_content = json.dumps({
            "item_id": "test:item:1",
            "pack": "test-pack",
            "domain": "credit_underwriting",
            "task": "case_review",
            "prompt": "Test prompt",
            "context": [],
            "deterministic_checks": [],
            "judges": [],
            "tags": {},
            "grading": {"disposition": "refer"},
        }) + "\n"

    items_path = pack_dir / "items.jsonl"
    items_path.write_text(items_content)

    items_sha = compute_file_sha256(items_path)

    manifest = {
        "pack_id": "test-pack",
        "version": "1.0.0",
        "domain": "credit_underwriting",
        "items": 1,
        "cases": 1,
        "items_sha256": items_sha,
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest))

    return pack_dir


def test_loader_accepts_valid_pack() -> None:
    """Loader should accept a pack with matching checksums."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = _create_test_pack(tmp)

        loader = PackLoader(verify=True)
        pack = loader.load(pack_dir)

        assert pack.manifest.pack_id == "test-pack"
        assert len(pack.items) == 1


def test_loader_rejects_tampered_items() -> None:
    """A one-byte edit to items.jsonl should make the loader refuse.

    This is acceptance criterion E1 from BUILD.md.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = _create_test_pack(tmp)

        items_path = pack_dir / "items.jsonl"
        original = items_path.read_text()
        tampered = original.replace("Test prompt", "Test prompt!")  # one char
        items_path.write_text(tampered)

        loader = PackLoader(verify=True)

        with pytest.raises(TamperError) as exc:
            loader.load(pack_dir)

        error = exc.value
        assert error.pack_id == "test-pack"
        assert "expected" in str(error).lower()
        assert "got" in str(error).lower()


def test_loader_skips_verification_when_disabled() -> None:
    """With verify=False, loader should not check checksums (but still parse)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = _create_test_pack(tmp)

        items_path = pack_dir / "items.jsonl"
        original = items_path.read_text()
        tampered = original.replace("Test prompt", "Tampered prompt")
        items_path.write_text(tampered)

        loader = PackLoader(verify=False)
        pack = loader.load(pack_dir)

        assert pack is not None
        assert pack.items[0].prompt == "Tampered prompt"


def test_loader_fails_on_missing_manifest() -> None:
    """Loader should fail clearly when manifest.json is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = tmp / "no-manifest"
        pack_dir.mkdir()
        (pack_dir / "items.jsonl").write_text("{}")

        loader = PackLoader()

        with pytest.raises(PackLoadError) as exc:
            loader.load(pack_dir)

        assert "manifest.json" in str(exc.value)


def test_loader_fails_on_missing_items() -> None:
    """Loader should fail clearly when items.jsonl is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = tmp / "no-items"
        pack_dir.mkdir()
        (pack_dir / "manifest.json").write_text(json.dumps({
            "pack_id": "x",
            "version": "1.0",
            "domain": "x",
            "items": 0,
            "cases": 0,
            "items_sha256": "x",
        }))

        loader = PackLoader()

        with pytest.raises(PackLoadError) as exc:
            loader.load(pack_dir)

        assert "items.jsonl" in str(exc.value)


def test_loader_fails_on_item_count_mismatch() -> None:
    """Loader should fail when item count doesn't match manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = _create_test_pack(tmp)

        manifest_path = pack_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["items"] = 99
        manifest_path.write_text(json.dumps(manifest))

        loader = PackLoader(verify=False)

        with pytest.raises(PackLoadError) as exc:
            loader.load(pack_dir)

        assert "mismatch" in str(exc.value).lower()


def test_compute_file_sha256_deterministic() -> None:
    """SHA256 computation should be deterministic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        test_file = tmp / "test.txt"
        test_file.write_text("Hello, World!")

        sha1 = compute_file_sha256(test_file)
        sha2 = compute_file_sha256(test_file)

        assert sha1 == sha2
        assert len(sha1) == 64


def test_pack_items_by_id() -> None:
    """Pack.items_by_id should return dict keyed by item_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pack_dir = _create_test_pack(tmp)

        loader = PackLoader()
        pack = loader.load(pack_dir)

        by_id = pack.items_by_id()
        assert "test:item:1" in by_id
        assert by_id["test:item:1"].item_id == "test:item:1"
