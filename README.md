# Credit Evidence Engine

Tests AI assistants that compile a case file for a human who makes a regulated
decision, and produces the evidence a second-line reviewer needs to approve them.

- `PLAN.md` — the four-week schedule and who does what
- `BUILD.md` — the specification and task tracker
- `docs/` — model selection, distillation note, Wednesday gate guide

## Run the Wednesday Gate

The Wednesday gate runs 20 cases through the full pipeline:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export NVIDIA_API_KEY=your_key_here  # or use --stub for testing
.venv/bin/python scripts/run_wed_gate.py
```

This runs: pack load → transcripts → marks → evidence report → verify.

For stub mode (no API calls):
```bash
.venv/bin/python scripts/run_wed_gate.py --stub
```

See `docs/WED_GATE.md` for full details.

## Run the Demo Gate (Week 1)

```bash
.venv/bin/python scripts/demo_gate.py
.venv/bin/pytest -q
```

`demo_gate.py` shows one generated referred case, a briefing that reads well and
omits the deciding fact, a briefing that surfaces it, and the omission check's
verdict on each. No model is called — the catch is arithmetic.

## What is where

| | |
|---|---|
| `specs/credit_underwriting.yaml` | The SDD recipe. A hidden capacity tier drives the observables; decoy fields have no path to the outcome. |
| `scripts/run_wed_gate.py` | Full pipeline: pack → transcripts → marks → evidence → verify. |
| `scripts/demo_gate.py` | Week 1 demo: one case, two briefings, the omission catch. |
| `src/evidence/engine/` | Runner (skip-if-exists), marker, loader with tamper detection. |
| `src/evidence/reporting/` | Evidence report generation and verification. |
| `src/evidence/checks/omission.py` | `material_omission`. Exact match, then similarity, then missing. Passes only at full marks. |
| `packs/underwriter-sample/` | Twenty referred cases, built. |

## Pipeline Components

1. **Runner** (`engine/runner.py`): Loads pack, calls Lightning (or stub), saves transcripts. Implements skip-if-exists for resume.
2. **Marker** (`engine/marker.py`): Runs omission checks on transcripts against the sealed answer key.
3. **Evidence** (`reporting/evidence.py`): Creates tamper-proof report with chain fingerprint.
4. **Verify** (`reporting/verify.py`): Recomputes fingerprints and catches any modification.

## Placeholders

The rule for *which* facts a briefing must surface (`omission_targets()` in the
pack builder) is a placeholder pending the materiality definition from Luca.
Replace the rule; do not tune the check around it.
