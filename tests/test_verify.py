# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Tests for evidence verification and tamper detection.

The tamper test is the demonstration from Week 3: change one digit in the
report by hand, and verification fails naming what went wrong.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from evidence.engine.loader import PackManifest
from evidence.engine.marker import ItemMarkResult, MarkResult
from evidence.reporting.evidence import (
    create_evidence_report,
    load_evidence_report,
    save_evidence_report,
)
from evidence.reporting.verify import (
    TamperVerificationError,
    verify_evidence_report,
)


def _create_test_setup(tmp: Path) -> tuple[PackManifest, MarkResult, Path]:
    """Create a minimal test setup with manifest, marks, and transcripts."""
    manifest = PackManifest(
        pack_id="test-pack",
        version="1.0.0",
        domain="credit_underwriting",
        items=2,
        cases=2,
        items_sha256="abc123def456",
        raw={},
    )

    marks = MarkResult(
        run_id="test-run",
        pack_id="test-pack",
        total=2,
        passed=1,
        failed=1,
        needs_audit=0,
        items=[
            ItemMarkResult(
                item_id="test:item:1",
                transcript_sha256="sha1",
                checks=[{"judge": "check:omission", "passed": True, "value": 1.0}],
                passed=True,
                failed_checks=[],
                needs_audit_count=0,
                marked_at="2026-09-15T00:00:00Z",
            ),
            ItemMarkResult(
                item_id="test:item:2",
                transcript_sha256="sha2",
                checks=[{"judge": "check:omission", "passed": False, "value": 0.5}],
                passed=False,
                failed_checks=["material_omission"],
                needs_audit_count=0,
                marked_at="2026-09-15T00:00:00Z",
            ),
        ],
        summary={"by_check": {"material_omission": {"passed": 1, "failed": 1}}},
    )

    transcripts_dir = tmp / "transcripts"
    transcripts_dir.mkdir(parents=True)

    (transcripts_dir / "test_item_1.json").write_text(json.dumps({
        "item_id": "test:item:1",
        "output": "Output 1",
        "sha256": "sha1",
    }))
    (transcripts_dir / "test_item_2.json").write_text(json.dumps({
        "item_id": "test:item:2",
        "output": "Output 2",
        "sha256": "sha2",
    }))

    return manifest, marks, transcripts_dir


def test_verify_passes_on_clean_report() -> None:
    """Verification should pass on an unmodified report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        result = verify_evidence_report(report)
        assert result is True


def test_verify_fails_on_tampered_chain_fingerprint() -> None:
    """Changing the chain fingerprint should fail verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        report.chain_fingerprint = "tampered_fingerprint_12345"

        with pytest.raises(TamperVerificationError) as exc:
            verify_evidence_report(report)

        assert "Chain fingerprint mismatch" in str(exc.value)


def test_verify_fails_on_tampered_report_file() -> None:
    """Changing a value in the report file should fail verification.

    This is the specific test from Week 3: change one digit by hand in the
    saved report file. This simulates someone editing the JSON directly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        report_path = tmp / "report.json"
        save_evidence_report(report, report_path)

        report_data = json.loads(report_path.read_text())
        original_passed = report_data["passed"]
        report_data["passed"] = original_passed + 1
        report_data["chain_fingerprint"] = "tampered" + report_data["chain_fingerprint"][8:]
        report_path.write_text(json.dumps(report_data))

        loaded = load_evidence_report(report_path)
        assert loaded.passed != original_passed

        with pytest.raises(TamperVerificationError) as exc:
            verify_evidence_report(loaded)

        assert "Chain fingerprint mismatch" in str(exc.value)


def test_verify_fails_on_modified_transcript() -> None:
    """Modifying a transcript file should fail verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        transcript_file = transcripts_dir / "test_item_1.json"
        modified = json.loads(transcript_file.read_text())
        modified["output"] = "MODIFIED OUTPUT"
        transcript_file.write_text(json.dumps(modified))

        with pytest.raises(TamperVerificationError) as exc:
            verify_evidence_report(report, run_dir=tmp)

        assert "Transcripts fingerprint mismatch" in str(exc.value)


def test_verify_fails_on_modified_marks() -> None:
    """Modifying the marks file should fail verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        marks_path = tmp / "marks.json"
        marks_path.write_text(json.dumps(marks.to_dict()))

        modified = json.loads(marks_path.read_text())
        modified["passed"] = 999
        marks_path.write_text(json.dumps(modified))

        with pytest.raises(TamperVerificationError) as exc:
            verify_evidence_report(report, run_dir=tmp)

        assert "Marks fingerprint mismatch" in str(exc.value)


def test_verify_fails_on_pack_fingerprint_mismatch() -> None:
    """Passing a different pack fingerprint should fail verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        with pytest.raises(TamperVerificationError) as exc:
            verify_evidence_report(report, pack_items_sha256="different_sha256")

        assert "Pack fingerprint mismatch" in str(exc.value)


def test_evidence_report_round_trip() -> None:
    """Evidence report should survive save/load round trip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        original = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        report_path = tmp / "report.json"
        save_evidence_report(original, report_path)
        loaded = load_evidence_report(report_path)

        assert loaded.report_id == original.report_id
        assert loaded.chain_fingerprint == original.chain_fingerprint
        assert loaded.passed == original.passed
        assert loaded.failed == original.failed
        assert loaded.total_items == original.total_items

        assert verify_evidence_report(loaded) is True


def test_tamper_detection_names_the_digit() -> None:
    """The error message should help locate what changed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest, marks, transcripts_dir = _create_test_setup(tmp)

        report = create_evidence_report(
            manifest=manifest,
            mark_result=marks,
            transcripts_dir=transcripts_dir,
        )

        report.chain_fingerprint = report.chain_fingerprint[:-1] + "X"

        with pytest.raises(TamperVerificationError) as exc:
            verify_evidence_report(report)

        error = exc.value
        assert error.report_id == report.report_id
        assert "Chain fingerprint" in str(error)
