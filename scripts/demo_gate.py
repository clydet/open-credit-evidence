# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The Week 1 gate, runnable: one real case, two briefings, the catch.

    python scripts/demo_gate.py [--case APP000044]

Prints the case as the underwriter would see it, a briefing that reads well and
omits the deciding fact, a briefing that surfaces it, and what the omission check
says about each. Nothing here calls a model — the point of the gate is that the
catch is arithmetic.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem

PACK = Path(__file__).resolve().parents[1] / "packs" / "underwriter-sample"


def _field(doc: str, label: str) -> str:
    m = re.search(rf"\| {re.escape(label)} \| (.+?) \|", doc)
    return m.group(1) if m else "?"


def briefings(item: BenchmarkItem) -> tuple[str, str]:
    """Two briefings for this case, both entirely true."""
    docs = {c.renderer: c.content for c in item.context}
    form = docs.get("application_form", "")
    bureau = docs.get("bureau_summary", "")
    score = re.search(r"\*\*(\d+)\*\*", bureau).group(1)
    file_age = _field(bureau, "Credit file opened")
    delinq = _field(bureau, "Delinquencies, last 24 months")
    employment = _field(form, "Employment type")
    tenure = _field(form, "Time in current role")
    verified = _field(form, "Income verified")
    amount = _field(form, "Amount")
    term = _field(form, "Term")
    instalment = _field(form, "Indicative monthly instalment")
    commitments = _field(form, "Existing monthly credit commitments")
    income = _field(form, "Gross annual income")
    top = item.grading.driver_labels[item.grading.driver_refs[0]]

    strengths = (
        f"Bureau score of {score} with a credit file open {file_age} and "
        f"{'no' if delinq == '0' else delinq} recorded delinquencies. "
        f"{employment.replace('_', ' ').capitalize()} employment, {tenure} in role, "
        f"income {'verified' if verified == 'Yes' else 'stated'}."
    )
    negative = (
        f"Strong applicant. {strengths} Affordability is somewhat tight but the "
        f"overall profile is sound. Recommend approval."
    )
    good = (
        f"Referred on affordability. The requested {amount} over {term} gives an "
        f"instalment of {instalment} which, with {commitments} of existing commitments "
        f"against {income} gross income, means {top}. This is the reason for referral. "
        f"Against that: {strengths} The case turns on the amount requested; a smaller "
        f"facility or higher verified income would change the outcome."
    )
    return negative, good


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="application id, e.g. APP000044")
    a = ap.parse_args()

    items = [BenchmarkItem.model_validate_json(line) for line in (PACK / "items.jsonl").open()]
    item = next((i for i in items if a.case and a.case in i.item_id), items[0])
    negative, good = briefings(item)

    print("=" * 78)
    print(f"CASE {item.item_id.split(':')[2]}   tags={item.tags}")
    print("=" * 78)
    for doc in item.context:
        print(f"\n--- {doc.renderer} ---")
        print(doc.content.strip())

    print("\n" + "=" * 78)
    print("WHAT A BRIEFING MUST SURFACE (from the marking key)")
    print("=" * 78)
    for ref in item.grading.omission_refs:
        print(f"  - {item.grading.omission_labels[ref]}")

    for title, text in (("BRIEFING A — reads well, every word true", negative),
                        ("BRIEFING B — surfaces the deciding fact", good)):
        print("\n" + "=" * 78)
        print(title)
        print("=" * 78)
        print(text)
        (r,) = run_checks(["material_omission"], output=text, item=item)
        print(f"\n  material_omission -> {'PASS' if r.passed else 'FAIL'}  "
              f"score {r.score:.2f}  needs_audit={r.needs_audit}")
        print(f"  {r.detail}")
        for e in r.evidence:
            mark = "found" if e["matched"] else "MISSING"
            via = f" via {e['method']}" if e.get("method") else ""
            print(f"    [{mark:7}] {e['ref']}{via}")

    print("\n" + "=" * 78)
    print("ENGINE RECORD for briefing A (what lands in the evidence pack)")
    print("=" * 78)
    (r,) = run_checks(["material_omission"], output=negative, item=item)
    rec = r.to_score()
    rec["evidence"] = [{k: v for k, v in e.items() if k != "span"} for e in rec["evidence"]]
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
