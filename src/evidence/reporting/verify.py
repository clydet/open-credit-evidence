# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Evidence report verification — the tamper detection test.

Recomputes all fingerprints from the source artifacts and verifies they
match what the report claims. If a single digit is changed anywhere in
the chain, verification fails and names what went wrong.

This is the demonstration from the Week 3 gate: change one digit in the
report by hand, and `oce verify` refuses it.
"""

from __future__ import annotations

import json
from pathlib import Path

from evidence.reporting.evidence import (
    EvidenceReport,
    compute_chain_fingerprint,
    compute_fingerprint,
    load_evidence_report,
)


class TamperVerificationError(Exception):
    """Raised when tampering is detected in an evidence report."""

    def __init__(self, report_id: str, reason: str, *, claim_id: str | None = None):
        self.report_id = report_id
        self.reason = reason
        self.claim_id = claim_id
        msg = f"Tamper detected in report {report_id}: {reason}"
        if claim_id:
            msg += f" (claim: {claim_id})"
        super().__init__(msg)


def _recompute_transcripts_fingerprint(transcripts_dir: Path) -> str:
    """Recompute fingerprint over all transcripts."""
    fingerprints: list[str] = []
    for f in sorted(transcripts_dir.glob("*.json")):
        if f.name == "run_manifest.json":
            continue
        content = f.read_text(encoding="utf-8")
        fingerprints.append(compute_fingerprint(content))

    if not fingerprints:
        return compute_fingerprint("")

    combined = "|".join(fingerprints)
    return compute_fingerprint(combined)


def _recompute_marks_fingerprint(marks_path: Path) -> str:
    """Recompute fingerprint of marking results."""
    marks_data = marks_path.read_text(encoding="utf-8")
    data = json.loads(marks_data)
    normalized = json.dumps(data, sort_keys=True)
    return compute_fingerprint(normalized)


def verify_evidence_report(
    report: EvidenceReport | Path,
    *,
    run_dir: Path | None = None,
    pack_items_sha256: str | None = None,
) -> bool:
    """Verify an evidence report has not been tampered with.

    This recomputes all fingerprints from source artifacts and verifies
    they match. If anything has changed, it fails with a descriptive error.

    Args:
        report: The report to verify (or path to load from)
        run_dir: Directory containing transcripts/ and marks.json
        pack_items_sha256: Optional items_sha256 to verify pack integrity

    Returns:
        True if verification passes

    Raises:
        TamperVerificationError: If tampering is detected
    """
    if isinstance(report, Path):
        report = load_evidence_report(report)

    if run_dir:
        transcripts_dir = run_dir / "transcripts"
        marks_path = run_dir / "marks.json"

        if transcripts_dir.exists():
            actual_transcripts_fp = _recompute_transcripts_fingerprint(transcripts_dir)
            if actual_transcripts_fp != report.transcripts_fingerprint:
                expected = report.transcripts_fingerprint[:16]
                actual = actual_transcripts_fp[:16]
                raise TamperVerificationError(
                    report.report_id,
                    f"Transcripts fingerprint mismatch: expected {expected}..., "
                    f"got {actual}...",
                )

        if marks_path.exists():
            actual_marks_fp = _recompute_marks_fingerprint(marks_path)
            if actual_marks_fp != report.marks_fingerprint:
                raise TamperVerificationError(
                    report.report_id,
                    f"Marks fingerprint mismatch: expected {report.marks_fingerprint[:16]}..., "
                    f"got {actual_marks_fp[:16]}...",
                )

    if pack_items_sha256:
        if pack_items_sha256 != report.pack_fingerprint:
            raise TamperVerificationError(
                report.report_id,
                f"Pack fingerprint mismatch: expected {report.pack_fingerprint[:16]}..., "
                f"got {pack_items_sha256[:16]}...",
            )

    expected_chain = compute_chain_fingerprint(
        report.pack_fingerprint,
        report.transcripts_fingerprint,
        report.marks_fingerprint,
    )

    if expected_chain != report.chain_fingerprint:
        raise TamperVerificationError(
            report.report_id,
            f"Chain fingerprint mismatch: expected {expected_chain[:16]}..., "
            f"got {report.chain_fingerprint[:16]}...",
        )

    return True


def verify_claim(
    report: EvidenceReport,
    claim_id: str,
    artifact_dir: Path,
) -> bool:
    """Verify a single claim traces to its source.

    Args:
        report: The evidence report
        claim_id: The claim to verify
        artifact_dir: Directory containing artifacts

    Returns:
        True if claim is valid

    Raises:
        TamperVerificationError: If claim does not match source
    """
    if claim_id not in report.claims:
        raise TamperVerificationError(
            report.report_id,
            f"Claim {claim_id} not found in report",
            claim_id=claim_id,
        )

    claim = report.claims[claim_id]
    artifact_path = artifact_dir / claim.artifact_uri

    if not artifact_path.exists():
        raise TamperVerificationError(
            report.report_id,
            f"Artifact {claim.artifact_uri} not found",
            claim_id=claim_id,
        )

    artifact_content = artifact_path.read_text(encoding="utf-8")
    data = json.loads(artifact_content)
    normalized = json.dumps(data, sort_keys=True)
    actual_sha = compute_fingerprint(normalized)

    if actual_sha != claim.artifact_sha256:
        raise TamperVerificationError(
            report.report_id,
            f"Artifact {claim.artifact_uri} has been modified",
            claim_id=claim_id,
        )

    return True
