#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Run the Wednesday gate: 20 cases → transcripts → marks → evidence.

    export NVIDIA_API_KEY=...        # or put it in .env, or run with --stub
    python scripts/run_wed_gate.py [--stub] [--pack PATH]

This script runs the full pipeline:
1. Load the 20-item underwriter pack
2. Run each item through Lightning (or stub mode)
3. Mark each transcript against the sealed answer key
4. Generate an evidence report with tamper-proof fingerprints
5. Verify the evidence report

With --stub, skips API calls and uses placeholder responses. Useful for
testing the pipeline without burning credits.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from evidence.engine import (  # noqa: E402
    BatchRunner,
    Marker,
    PackLoader,
    RunConfig,
    load_transcripts,
    save_mark_results,
)
from evidence.reporting import (  # noqa: E402
    create_evidence_report,
    save_evidence_report,
    verify_evidence_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Wednesday gate: cases → transcripts → marks → evidence"
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=REPO_ROOT / "packs" / "underwriter-sample",
        help="Path to pack directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for run results (default: pack/runs/<run_id>)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier (default: auto-generated timestamp)",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Use stub responses (no API calls)",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        help="Use RAG retrieval (requires embed endpoint)",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip running transcripts, only mark existing ones",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("WEDNESDAY GATE — Credit Evidence Engine")
    print("=" * 70)

    # Step 1: Load the pack
    print(f"\n[1/5] Loading pack: {args.pack}")
    try:
        loader = PackLoader(verify=True)
        pack = loader.load(args.pack)
        print(f"  Pack: {pack.manifest.pack_id} v{pack.manifest.version}")
        print(f"  Items: {len(pack.items)}")
        print(f"  SHA256: {pack.manifest.items_sha256[:16]}...")
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    # Configure the run
    config = RunConfig(
        run_id=args.run_id,
        use_rag=args.rag,
        skip_existing=True,
        stub=args.stub,
        output_dir=args.output,
    )

    output_dir = config.output_dir or (pack.path / "runs" / config.run_id)
    transcripts_dir = output_dir / "transcripts"

    # Step 2: Run items through the assistant
    if args.skip_run:
        print("\n[2/5] Skipping runner (--skip-run), using existing transcripts")
        if not transcripts_dir.exists():
            print(f"  ERROR: No transcripts found at {transcripts_dir}")
            return 1
    else:
        print(f"\n[2/5] Running {len(pack.items)} items through assistant...")
        print(f"  Mode: {'STUB' if args.stub else 'LIVE (Lightning)'}")
        print(f"  RAG: {'ON' if args.rag else 'OFF (whole-file)'}")
        print(f"  Output: {output_dir}")

        runner = BatchRunner(config=config)
        result = runner.run(pack)

        print("\n  Results:")
        print(f"    Processed: {result.processed}")
        print(f"    Skipped:   {result.skipped} (already existed)")
        print(f"    Failed:    {result.failed}")

        if result.errors and args.verbose:
            print("    Errors:")
            for item_id, error in result.errors:
                print(f"      {item_id}: {error}")

    # Step 3: Mark transcripts
    print("\n[3/5] Marking transcripts against answer key...")
    transcripts = load_transcripts(transcripts_dir)
    items_by_id = pack.items_by_id()

    print(f"  Loaded {len(transcripts)} transcripts")

    marker = Marker()
    mark_result = marker.mark_run(
        items=items_by_id,
        transcripts=transcripts,
        run_id=config.run_id,
        pack_id=pack.manifest.pack_id,
    )

    marks_path = output_dir / "marks.json"
    save_mark_results(mark_result, marks_path)

    print("\n  Marking results:")
    print(f"    Total:       {mark_result.total}")
    print(f"    Passed:      {mark_result.passed}")
    print(f"    Failed:      {mark_result.failed}")
    print(f"    Needs audit: {mark_result.needs_audit}")

    if mark_result.summary.get("by_check"):
        print("\n  By check:")
        for check_name, counts in mark_result.summary["by_check"].items():
            print(f"    {check_name}: {counts['passed']} pass, {counts['failed']} fail")

    # Show failed items
    failed_items = [i for i in mark_result.items if not i.passed]
    if failed_items and args.verbose:
        print("\n  Failed items:")
        for item in failed_items:
            print(f"    {item.item_id}: {item.failed_checks}")

    # Step 4: Generate evidence report
    print("\n[4/5] Generating evidence report...")
    evidence = create_evidence_report(
        manifest=pack.manifest,
        mark_result=mark_result,
        transcripts_dir=transcripts_dir,
        metadata={
            "generator": "run_wed_gate.py",
            "stub_mode": args.stub,
            "rag_mode": args.rag,
        },
    )

    report_path = output_dir / "evidence_report.json"
    save_evidence_report(evidence, report_path)

    print(f"  Report ID:    {evidence.report_id}")
    print(f"  Chain FP:     {evidence.chain_fingerprint[:16]}...")
    print(f"  Pass rate:    {evidence.pass_rate:.1%}")
    print(f"  Saved to:     {report_path}")

    # Step 5: Verify evidence report
    print("\n[5/5] Verifying evidence report (tamper check)...")
    try:
        verify_evidence_report(
            evidence,
            run_dir=output_dir,
            pack_items_sha256=pack.manifest.items_sha256,
        )
        print("  ✓ Verification PASSED — no tampering detected")
    except Exception as e:
        print(f"  ✗ Verification FAILED: {e}")
        return 2

    # Summary
    print("\n" + "=" * 70)
    print("WEDNESDAY GATE COMPLETE")
    print("=" * 70)
    print(f"\nRun directory: {output_dir}")
    print(f"  transcripts/     - {len(transcripts)} transcript files")
    print("  marks.json       - marking results")
    print("  evidence_report.json - tamper-proof evidence")
    print("  run_manifest.json    - run metadata")

    if mark_result.failed > 0:
        print(f"\n⚠ {mark_result.failed} item(s) failed the omission check.")
        print("  This is expected for the negative control case.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
