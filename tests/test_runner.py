# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Tests for the batch runner: skip-if-exists, resume, and transcript recording."""

from __future__ import annotations

import tempfile
from pathlib import Path

from evidence.contracts.item import BenchmarkItem, GradingSpec, ItemContext
from evidence.contracts.transcript import SUTPins, Transcript
from evidence.engine.runner import BatchRunner, RunConfig, load_transcripts

SAMPLE_ITEM = BenchmarkItem(
    item_id="test:case_review:APP000001:complete",
    pack="test",
    domain="credit_underwriting",
    task="case_review",
    prompt="Summarise this case.",
    context=[
        ItemContext(
            renderer="application_form",
            variant="complete",
            content="Gross annual income £17,100. Amount £21,100.",
        ),
    ],
    deterministic_checks=["material_omission"],
    grading=GradingSpec(
        disposition="refer",
        omission_refs=["dti_ratio"],
        omission_labels={"dti_ratio": "debt-to-income ratio exceeds policy"},
    ),
)


class MockAdapter:
    """Mock adapter that tracks calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.call_count = 0

    def answer(
        self, item: BenchmarkItem, *, use_rag: bool = False
    ) -> tuple[str, SUTPins, list, dict[str, int]]:
        self.calls.append(item.item_id)
        self.call_count += 1

        sut = SUTPins(
            model_id="mock",
            prompt_version="mock123",
            params={"mock": True},
        )
        return (
            f"Mock output for {item.item_id}",
            sut,
            [],
            {"latency_ms": 10, "tokens_in": 50, "tokens_out": 25},
        )


def test_runner_skip_if_exists() -> None:
    """Runner should skip items that already have transcripts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        transcripts_dir = tmp / "transcripts"
        transcripts_dir.mkdir(parents=True)

        existing_transcript = Transcript(
            item_id=SAMPLE_ITEM.item_id,
            run_id="existing-run",
            sut=SUTPins(model_id="old", prompt_version="old123", params={}),
            system_prompt="old system",
            user_prompt="old user",
            output="Old output from previous run",
            latency_ms=100,
            tokens_in=10,
            tokens_out=20,
            started_at="2026-09-15T00:00:00Z",
            sha256="abc123",
        )

        safe_id = SAMPLE_ITEM.item_id.replace(":", "_")
        transcript_path = transcripts_dir / f"{safe_id}.json"
        transcript_path.write_text(existing_transcript.model_dump_json())

        adapter = MockAdapter()
        config = RunConfig(
            run_id="test-run",
            skip_existing=True,
            output_dir=tmp,
        )
        runner = BatchRunner(adapter=adapter, config=config)

        class FakePack:
            items = [SAMPLE_ITEM]
            manifest = type("M", (), {
                "pack_id": "test",
                "version": "0.1",
                "items_sha256": "fake",
            })()
            path = tmp

        result = runner.run(FakePack())

        assert adapter.call_count == 0, "Adapter should not be called for existing transcript"
        assert result.skipped == 1
        assert result.processed == 0

        loaded = load_transcripts(transcripts_dir)
        assert SAMPLE_ITEM.item_id in loaded
        assert loaded[SAMPLE_ITEM.item_id].output == "Old output from previous run"


def test_runner_processes_new_items() -> None:
    """Runner should process items without existing transcripts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        adapter = MockAdapter()
        config = RunConfig(
            run_id="test-run",
            skip_existing=True,
            output_dir=tmp,
        )
        runner = BatchRunner(adapter=adapter, config=config)

        class FakePack:
            items = [SAMPLE_ITEM]
            manifest = type("M", (), {
                "pack_id": "test",
                "version": "0.1",
                "items_sha256": "fake",
            })()
            path = tmp

        result = runner.run(FakePack())

        assert adapter.call_count == 1
        assert result.processed == 1
        assert result.skipped == 0


def test_runner_resume_partial_run() -> None:
    """Runner should resume by processing only missing items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        transcripts_dir = tmp / "transcripts"
        transcripts_dir.mkdir(parents=True)

        item1 = SAMPLE_ITEM
        item2 = BenchmarkItem(
            item_id="test:case_review:APP000002:complete",
            pack="test",
            domain="credit_underwriting",
            task="case_review",
            prompt="Summarise this case.",
            context=[ItemContext(renderer="form", variant="v1", content="Content")],
            deterministic_checks=[],
            grading=GradingSpec(disposition="refer"),
        )

        existing = Transcript(
            item_id=item1.item_id,
            run_id="partial",
            sut=SUTPins(model_id="old", prompt_version="old", params={}),
            system_prompt="sys",
            user_prompt="usr",
            output="Done already",
            latency_ms=10,
            tokens_in=5,
            tokens_out=5,
            started_at="2026-09-15T00:00:00Z",
            sha256="xyz",
        )

        safe_id = item1.item_id.replace(":", "_")
        (transcripts_dir / f"{safe_id}.json").write_text(existing.model_dump_json())

        adapter = MockAdapter()
        config = RunConfig(run_id="partial", skip_existing=True, output_dir=tmp)
        runner = BatchRunner(adapter=adapter, config=config)

        class FakePack:
            items = [item1, item2]
            manifest = type("M", (), {
                "pack_id": "test",
                "version": "0.1",
                "items_sha256": "fake",
            })()
            path = tmp

        result = runner.run(FakePack())

        assert adapter.call_count == 1
        assert adapter.calls == [item2.item_id]
        assert result.processed == 1
        assert result.skipped == 1


def test_runner_force_reprocess() -> None:
    """With skip_existing=False, runner should reprocess existing items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        transcripts_dir = tmp / "transcripts"
        transcripts_dir.mkdir(parents=True)

        existing = Transcript(
            item_id=SAMPLE_ITEM.item_id,
            run_id="old",
            sut=SUTPins(model_id="old", prompt_version="old", params={}),
            system_prompt="sys",
            user_prompt="usr",
            output="Old output",
            latency_ms=10,
            tokens_in=5,
            tokens_out=5,
            started_at="2026-09-15T00:00:00Z",
            sha256="xyz",
        )

        safe_id = SAMPLE_ITEM.item_id.replace(":", "_")
        (transcripts_dir / f"{safe_id}.json").write_text(existing.model_dump_json())

        adapter = MockAdapter()
        config = RunConfig(run_id="new", skip_existing=False, output_dir=tmp)
        runner = BatchRunner(adapter=adapter, config=config)

        class FakePack:
            items = [SAMPLE_ITEM]
            manifest = type("M", (), {
                "pack_id": "test",
                "version": "0.1",
                "items_sha256": "fake",
            })()
            path = tmp

        result = runner.run(FakePack())

        assert adapter.call_count == 1
        assert result.processed == 1
        assert result.skipped == 0

        loaded = load_transcripts(transcripts_dir)
        assert "Mock output" in loaded[SAMPLE_ITEM.item_id].output
