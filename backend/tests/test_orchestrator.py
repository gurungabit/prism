import asyncio
from datetime import UTC, datetime

from src.agents import orchestrator
from src.agents.state_codec import checkpoint_safe_update, normalize_chunks
from src.models.report import AnalysisInput
from src.models.chunk import Chunk, ChunkMetadata


class FakeApp:
    def __init__(self) -> None:
        self.initial_state = None
        self.config = None

    async def ainvoke(self, initial_state, config=None):
        self.initial_state = initial_state
        self.config = config
        return {
            "final_report": {
                "analysis_id": initial_state["analysis_id"],
                "requirement": initial_state["requirement"],
            }
        }


def test_run_analysis_does_not_checkpoint_function(monkeypatch):
    fake_app = FakeApp()

    async def fake_create_compiled_app(checkpointer=None):
        return fake_app

    monkeypatch.setattr(orchestrator, "create_compiled_app", fake_create_compiled_app)

    callback_calls = []

    async def on_step(step_data: dict) -> None:
        callback_calls.append(step_data)

    report = asyncio.run(
        orchestrator.run_analysis(
            requirement="Add MFA to customer portal",
            analysis_id="analysis-test",
            analysis_input=AnalysisInput(requirement="Add MFA to customer portal"),
            on_step=on_step,
        )
    )

    assert report.analysis_id == "analysis-test"
    assert fake_app.initial_state is not None
    assert "on_step" not in fake_app.initial_state
    assert fake_app.initial_state["analysis_id"] == "analysis-test"
    assert orchestrator.get_step_callback("analysis-test") is None


class FakeGraphDateTime:
    def isoformat(self) -> str:
        return "2026-04-07T12:00:00+00:00"


def test_checkpoint_safe_update_serializes_temporal_objects():
    update = {
        "conflicts": [
            {
                "service": "orders",
                "owners": [{"team": "Payments", "updated": FakeGraphDateTime()}],
            }
        ]
    }

    serialized = checkpoint_safe_update(update)

    assert serialized["conflicts"][0]["owners"][0]["updated"] == "2026-04-07T12:00:00+00:00"


def test_normalize_chunks_round_trip_from_checkpoint_payload():
    chunks = [
        Chunk(
            chunk_id="c1",
            document_id="d1",
            content="hello",
            metadata=ChunkMetadata(
                source_platform="gitlab",
                source_path="docs/a.md",
                document_title="A",
                last_modified=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
            ),
        )
    ]

    serialized = checkpoint_safe_update({"retrieved_chunks": chunks})
    restored = normalize_chunks(serialized["retrieved_chunks"])

    assert restored[0].metadata.source_path == "docs/a.md"
    assert restored[0].metadata.last_modified is not None
