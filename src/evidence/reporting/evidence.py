# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Evidence report generation with tamper-proof fingerprinting.

Creates evidence reports that chain together the pack, transcripts, and
marking results with cryptographic fingerprints. Every number in the
report traces back to a verifiable artifact.

Adapted from Algoritmica patterns for this fork's contracts and layout.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.engine.loader import PackManifest
from evidence.engine.marker import MarkResult


def compute_fingerprint(content: str) -> str:
    """Compute SHA-256 fingerprint of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_chain_fingerprint(
    pack_fingerprint: str,
    transcripts_fingerprint: str,
    marks_fingerprint: str,
) -> str:
    """Compute the evidence chain fingerprint.

    Ties together pack, transcripts, and marking into a single verifiable hash.
    This is what the verifier recomputes to detect tampering.
    """
    chain = f"{pack_fingerprint}|{transcripts_fingerprint}|{marks_fingerprint}"
    return compute_fingerprint(chain)


@dataclass
class Claim:
    """A traceable claim in the evidence report.

    Every number in the report is a claim with a binding to its source
    artifact and the path within that artifact. No number is ever typed.
    """

    claim_id: str
    value: Any
    artifact_uri: str
    json_path: str
    artifact_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "value": self.value,
            "artifact_uri": self.artifact_uri,
            "json_path": self.json_path,
            "artifact_sha256": self.artifact_sha256,
        }


@dataclass
class EvidenceReport:
    """A tamper-proof evidence report.

    Organized by obligation, with every figure traced to its source.
    """

    report_id: str
    run_id: str
    pack_id: str
    pack_version: str

    pack_fingerprint: str
    transcripts_fingerprint: str
    marks_fingerprint: str
    chain_fingerprint: str

    total_items: int
    passed: int
    failed: int
    needs_audit: int
    pass_rate: float

    claims: dict[str, Claim]
    summary_by_check: dict[str, dict[str, int]]

    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "run_id": self.run_id,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "pack_fingerprint": self.pack_fingerprint,
            "transcripts_fingerprint": self.transcripts_fingerprint,
            "marks_fingerprint": self.marks_fingerprint,
            "chain_fingerprint": self.chain_fingerprint,
            "total_items": self.total_items,
            "passed": self.passed,
            "failed": self.failed,
            "needs_audit": self.needs_audit,
            "pass_rate": self.pass_rate,
            "claims": {k: v.to_dict() for k, v in self.claims.items()},
            "summary_by_check": self.summary_by_check,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


def generate_report_id() -> str:
    """Generate a unique report ID."""
    ts = datetime.now(UTC).strftime("%Y%m%d")
    return f"EVR-{ts}-{uuid.uuid4().hex[:8].upper()}"


def _compute_transcripts_fingerprint(transcripts_dir: Path) -> str:
    """Compute fingerprint over all transcripts."""
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


def _compute_marks_fingerprint(mark_result: MarkResult) -> str:
    """Compute fingerprint of marking results."""
    marks_data = json.dumps(mark_result.to_dict(), sort_keys=True)
    return compute_fingerprint(marks_data)


def create_evidence_report(
    manifest: PackManifest,
    mark_result: MarkResult,
    transcripts_dir: Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> EvidenceReport:
    """Create a tamper-proof evidence report.

    Args:
        manifest: The pack manifest
        mark_result: The marking results
        transcripts_dir: Directory containing transcript files
        metadata: Optional additional metadata

    Returns:
        EvidenceReport with chain fingerprint
    """
    report_id = generate_report_id()

    pack_fp = manifest.items_sha256
    transcripts_fp = _compute_transcripts_fingerprint(transcripts_dir)
    marks_fp = _compute_marks_fingerprint(mark_result)
    chain_fp = compute_chain_fingerprint(pack_fp, transcripts_fp, marks_fp)

    claims: dict[str, Claim] = {}

    claims["total_items"] = Claim(
        claim_id="total_items",
        value=mark_result.total,
        artifact_uri="marks.json",
        json_path="$.total",
        artifact_sha256=marks_fp,
    )
    claims["passed"] = Claim(
        claim_id="passed",
        value=mark_result.passed,
        artifact_uri="marks.json",
        json_path="$.passed",
        artifact_sha256=marks_fp,
    )
    claims["failed"] = Claim(
        claim_id="failed",
        value=mark_result.failed,
        artifact_uri="marks.json",
        json_path="$.failed",
        artifact_sha256=marks_fp,
    )
    claims["needs_audit"] = Claim(
        claim_id="needs_audit",
        value=mark_result.needs_audit,
        artifact_uri="marks.json",
        json_path="$.needs_audit",
        artifact_sha256=marks_fp,
    )

    pass_rate = mark_result.passed / mark_result.total if mark_result.total > 0 else 0.0

    return EvidenceReport(
        report_id=report_id,
        run_id=mark_result.run_id,
        pack_id=manifest.pack_id,
        pack_version=manifest.version,
        pack_fingerprint=pack_fp,
        transcripts_fingerprint=transcripts_fp,
        marks_fingerprint=marks_fp,
        chain_fingerprint=chain_fp,
        total_items=mark_result.total,
        passed=mark_result.passed,
        failed=mark_result.failed,
        needs_audit=mark_result.needs_audit,
        pass_rate=round(pass_rate, 4),
        claims=claims,
        summary_by_check=mark_result.summary.get("by_check", {}),
        created_at=datetime.now(UTC).isoformat(),
        metadata=metadata or {},
    )


def save_evidence_report(report: EvidenceReport, output_path: Path) -> None:
    """Save evidence report to JSON."""
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )


def load_evidence_report(input_path: Path) -> EvidenceReport:
    """Load evidence report from JSON."""
    data = json.loads(input_path.read_text(encoding="utf-8"))

    claims = {
        k: Claim(
            claim_id=v["claim_id"],
            value=v["value"],
            artifact_uri=v["artifact_uri"],
            json_path=v["json_path"],
            artifact_sha256=v["artifact_sha256"],
        )
        for k, v in data.get("claims", {}).items()
    }

    return EvidenceReport(
        report_id=data["report_id"],
        run_id=data["run_id"],
        pack_id=data["pack_id"],
        pack_version=data["pack_version"],
        pack_fingerprint=data["pack_fingerprint"],
        transcripts_fingerprint=data["transcripts_fingerprint"],
        marks_fingerprint=data["marks_fingerprint"],
        chain_fingerprint=data["chain_fingerprint"],
        total_items=data["total_items"],
        passed=data["passed"],
        failed=data["failed"],
        needs_audit=data["needs_audit"],
        pass_rate=data["pass_rate"],
        claims=claims,
        summary_by_check=data.get("summary_by_check", {}),
        created_at=data["created_at"],
        metadata=data.get("metadata", {}),
    )
