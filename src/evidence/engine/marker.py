# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Marker: runs checks on transcripts against the sealed answer key.

The marker orchestrates running all deterministic checks on each transcript
and recording the results. It uses the item's grading spec (the answer key)
to evaluate the model's output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.contracts.transcript import Transcript


@dataclass
class ItemMarkResult:
    """Marking result for a single item."""

    item_id: str
    transcript_sha256: str
    checks: list[dict[str, Any]]
    passed: bool
    failed_checks: list[str]
    needs_audit_count: int
    marked_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "transcript_sha256": self.transcript_sha256,
            "checks": self.checks,
            "passed": self.passed,
            "failed_checks": self.failed_checks,
            "needs_audit_count": self.needs_audit_count,
            "marked_at": self.marked_at,
        }


@dataclass
class MarkResult:
    """Overall marking result for a run."""

    run_id: str
    pack_id: str
    total: int
    passed: int
    failed: int
    needs_audit: int
    items: list[ItemMarkResult]
    summary: dict[str, Any] = field(default_factory=dict)
    marked_at: str = ""

    def __post_init__(self) -> None:
        if not self.marked_at:
            self.marked_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pack_id": self.pack_id,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "needs_audit": self.needs_audit,
            "items": [i.to_dict() for i in self.items],
            "summary": self.summary,
            "marked_at": self.marked_at,
        }


class Marker:
    """Runs checks on transcripts and records results."""

    def __init__(self, checks: list[str] | None = None):
        """Initialize marker.

        Args:
            checks: List of check names to run. If None, uses each item's
                   deterministic_checks list.
        """
        self.default_checks = checks

    def mark_item(
        self,
        item: BenchmarkItem,
        transcript: Transcript,
        *,
        checks: list[str] | None = None,
    ) -> ItemMarkResult:
        """Run checks on a single item's transcript."""
        check_names = checks or self.default_checks or item.deterministic_checks

        results = run_checks(check_names, output=transcript.output, item=item)

        passed = all(r.passed for r in results)
        failed_checks = [r.name for r in results if not r.passed]
        needs_audit = sum(1 for r in results if r.needs_audit)

        return ItemMarkResult(
            item_id=item.item_id,
            transcript_sha256=transcript.sha256,
            checks=[r.to_score() for r in results],
            passed=passed,
            failed_checks=failed_checks,
            needs_audit_count=needs_audit,
            marked_at=datetime.now(UTC).isoformat(),
        )

    def mark_run(
        self,
        items: dict[str, BenchmarkItem],
        transcripts: dict[str, Transcript],
        *,
        run_id: str,
        pack_id: str,
    ) -> MarkResult:
        """Mark all transcripts in a run.

        Args:
            items: Map of item_id -> BenchmarkItem
            transcripts: Map of item_id -> Transcript
            run_id: The run identifier
            pack_id: The pack identifier

        Returns:
            MarkResult with all item results and aggregates
        """
        results: list[ItemMarkResult] = []
        check_counts: dict[str, dict[str, int]] = {}

        for item_id, transcript in transcripts.items():
            if item_id not in items:
                continue

            item = items[item_id]
            result = self.mark_item(item, transcript)
            results.append(result)

            for check_data in result.checks:
                name = check_data["judge"].replace("check:", "")
                if name not in check_counts:
                    check_counts[name] = {"passed": 0, "failed": 0, "needs_audit": 0}
                if check_data["passed"]:
                    check_counts[name]["passed"] += 1
                else:
                    check_counts[name]["failed"] += 1
                if check_data.get("needs_audit"):
                    check_counts[name]["needs_audit"] += 1

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        needs_audit = sum(1 for r in results if r.needs_audit_count > 0)

        return MarkResult(
            run_id=run_id,
            pack_id=pack_id,
            total=len(results),
            passed=passed,
            failed=failed,
            needs_audit=needs_audit,
            items=results,
            summary={"by_check": check_counts},
        )


def save_mark_results(result: MarkResult, output_path: Path) -> None:
    """Save marking results to a JSON file."""
    output_path.write_text(
        json.dumps(result.to_dict(), indent=2), encoding="utf-8"
    )


def load_mark_results(input_path: Path) -> MarkResult:
    """Load marking results from a JSON file."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = [
        ItemMarkResult(
            item_id=i["item_id"],
            transcript_sha256=i["transcript_sha256"],
            checks=i["checks"],
            passed=i["passed"],
            failed_checks=i["failed_checks"],
            needs_audit_count=i["needs_audit_count"],
            marked_at=i["marked_at"],
        )
        for i in data["items"]
    ]
    return MarkResult(
        run_id=data["run_id"],
        pack_id=data["pack_id"],
        total=data["total"],
        passed=data["passed"],
        failed=data["failed"],
        needs_audit=data["needs_audit"],
        items=items,
        summary=data.get("summary", {}),
        marked_at=data["marked_at"],
    )
