# Running the Wednesday Gate

The Wednesday gate runs 20 cases through the full pipeline:
cases → transcripts → marks → evidence. This document explains how
to run it and what to expect.

## Quick Start with Docker Compose

The easiest way to run the gate:

```bash
# Stub mode (default command, no API key needed)
docker compose run --rm evidence

# Live mode (needs NVIDIA_API_KEY in .env)
cp .env.example .env
# Edit .env with your API key
docker compose run --rm evidence python scripts/run_wed_gate.py
```

Outputs persist in `./packs/underwriter-sample/runs/` on your host.

## Docker Compose Services

| Service | Description | Example |
|---------|-------------|---------|
| `evidence` | Run the Wednesday gate | `docker compose run --rm evidence` |
| `test` | Run all tests | `docker compose run --rm test` |
| `demo` | Show Week 1 demo gate | `docker compose run --rm demo` |

### Compose Commands

**Note:** `docker compose run SERVICE [CMD...]` replaces the entire command.
The `evidence` service defaults to stub mode. To run live or with options,
specify the full command.

```bash
# Build the image
docker compose build

# Stub mode (default)
docker compose run --rm evidence

# Live mode (no --stub flag)
docker compose run --rm evidence python scripts/run_wed_gate.py

# Live mode with RAG
docker compose run --rm evidence python scripts/run_wed_gate.py --rag

# Stub with specific run ID
docker compose run --rm evidence python scripts/run_wed_gate.py --stub --run-id my-run

# Run tests
docker compose run --rm test

# Run demo gate
docker compose run --rm demo

# View help
docker compose run --rm evidence python scripts/run_wed_gate.py --help
```

### Volume Mounts

The compose setup mounts these directories:
- `./packs` → `/app/packs` — all run outputs persist here
- `./specs` → `/app/specs` — SDD specifications

Run artifacts appear at `./packs/underwriter-sample/runs/<run_id>/` on your host.

---

## Running Locally (without Docker)

### Prerequisites

1. **Python 3.12+** with the package installed:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

2. **NVIDIA API Key** (for live runs):
   ```bash
   export NVIDIA_API_KEY=your_key_here
   # or put it in a gitignored .env file
   ```

### Quick Start (Stub Mode)

Run without API calls to test the pipeline:

```bash
.venv/bin/python scripts/run_wed_gate.py --stub
```

This creates transcripts with stub responses, runs the omission check,
generates an evidence report, and verifies it.

### Live Run

Run with actual NVIDIA Lightning calls:

```bash
.venv/bin/python scripts/run_wed_gate.py
```

**Note:** Live calls take ~10 seconds each. The runner saves progress
and skips items that already have transcripts, so you can safely
interrupt and resume.

### With RAG Retrieval

Enable RAG to select relevant chunks instead of whole-file context:

```bash
.venv/bin/python scripts/run_wed_gate.py --rag
```

## Command Options

```
--pack PATH       Path to pack directory (default: packs/underwriter-sample)
--output PATH     Output directory (default: pack/runs/<run_id>)
--run-id ID       Run identifier (default: auto-generated timestamp)
--stub            Use stub responses (no API calls)
--rag             Use RAG retrieval
--skip-run        Skip running transcripts, only mark existing ones
-v, --verbose     Verbose output
```

## Output Structure

After a run, you'll find:

```
packs/underwriter-sample/runs/<run_id>/
  transcripts/           # One JSON file per item
    underwriter-sample_case_review_APP000044_complete.json
    ...
  marks.json             # Marking results for all items
  evidence_report.json   # Tamper-proof evidence report
  run_manifest.json      # Run metadata
```

## Understanding the Output

### Marking Results

The `marks.json` file contains:
- `total`: Number of items marked
- `passed`: Items that passed all checks
- `failed`: Items that failed at least one check
- `needs_audit`: Items with similarity matches (not exact)
- `items`: Per-item results
- `summary.by_check`: Aggregates by check name

### Evidence Report

The `evidence_report.json` contains:
- `chain_fingerprint`: Cryptographic hash tying together pack, transcripts, and marks
- `claims`: Every number with its source artifact binding
- `pass_rate`: Fraction of items that passed

### Verification

The gate automatically verifies the evidence report:
```
✓ Verification PASSED — no tampering detected
```

To manually verify later:
```python
from evidence.reporting import load_evidence_report, verify_evidence_report

report = load_evidence_report("path/to/evidence_report.json")
verify_evidence_report(report, run_dir="path/to/run/dir")
```

## Expected Results

For the 20-item underwriter pack:
- Most items should **fail** `material_omission` in stub mode (stubs don't contain the required facts)
- In live mode, results depend on model performance
- The negative control case (deliberately omitting the deciding fact) should always fail

## Troubleshooting

### "NVIDIA_API_KEY is not set"

Set your API key:
```bash
export NVIDIA_API_KEY=your_key
```

Or use stub mode for testing:
```bash
.venv/bin/python scripts/run_wed_gate.py --stub
```

### Resuming an Interrupted Run

The runner automatically skips items with existing transcripts:
```bash
.venv/bin/python scripts/run_wed_gate.py --run-id <existing-run-id>
```

### Re-running from Scratch

To force reprocessing all items, either:
1. Use a new run ID (default behavior)
2. Delete the existing run directory
3. Modify the config to disable skip-existing (programmatically)

## Next Steps

After the gate passes:
1. Review failed items to understand the omission patterns
2. Examine `needs_audit` items that relied on similarity matching
3. Use the evidence report for regulatory documentation
