#!/usr/bin/env python3
"""Summarize feedback-backed cases for retrieval/report evaluation.

Usage:
    uv run python scripts/eval_feedback.py --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "backend")
)

from src.ingestion.analysis_store import AnalysisRepository  # noqa: E402
from src.observability.logging import setup_logging  # noqa: E402


async def run(limit: int) -> None:
    setup_logging()
    repo = await AnalysisRepository.create()
    try:
        rows = await repo.list_feedback(limit=limit)
    finally:
        await repo.close()

    cases = []
    for row in rows:
        report = row.get("report") or {}
        if isinstance(report, str):
            report = json.loads(report)
        cases.append(
            {
                "analysis_id": row["analysis_id"],
                "requirement": row["requirement"],
                "section": row["section"],
                "correct_answer": row["correct_answer"],
                "reason": row["reason"],
                "reported_sources": [
                    source.get("path")
                    for source in (report.get("all_sources") or [])[:10]
                    if isinstance(source, dict)
                ],
            }
        )

    print(json.dumps({"count": len(cases), "cases": cases}, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export PRISM feedback eval cases")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(run(args.limit))


if __name__ == "__main__":
    main()
