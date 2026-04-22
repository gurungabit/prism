#!/usr/bin/env python3
"""CLI for triggering an ingest run on a declared source.

The web UI is the main entry point (the setup wizard + source detail page
both have "Sync now" buttons). This script exists so CI and admins can drive
ingestion without opening a browser.

Usage:
    uv run python scripts/ingest.py --source-id <uuid>
    uv run python scripts/ingest.py --source-id <uuid> --force
    uv run python scripts/ingest.py --list
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "backend")
)

from src.catalog import SourceRepository  # noqa: E402
from src.ingestion.pipeline import IngestionPipeline  # noqa: E402
from src.observability.logging import setup_logging  # noqa: E402


async def run(source_id: UUID, force: bool) -> None:
    setup_logging()
    pipeline = await IngestionPipeline.create()
    try:
        stats = await pipeline.ingest_source(source_id, force=force)
        print("\nIngestion complete:")
        print(f"  Source: {stats['source_id']}")
        print(f"  Total:  {stats['total']}")
        print(f"  Indexed: {stats['indexed']}")
        print(f"  Skipped (unchanged): {stats['skipped']}")
        print(f"  Failed:  {stats['failed']}")
    finally:
        await pipeline.close()


async def list_sources() -> None:
    setup_logging()
    repo = await SourceRepository.create()
    try:
        sources = await repo.list_sources()
        if not sources:
            print("No declared sources. Use the web UI to attach one first.")
            return
        print(f"{'id':36}  {'kind':12}  {'status':9}  name")
        for src in sources:
            print(f"{str(src.id):36}  {src.kind.value:12}  {src.status.value:9}  {src.name}")
    finally:
        await repo.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="PRISM declared-source ingestion")
    parser.add_argument("--source-id", type=str, help="UUID of the declared source to ingest")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force full re-index (wipes existing chunks and skips content-hash checks)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all declared sources and exit",
    )
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_sources())
        return

    if not args.source_id:
        parser.error("either --source-id or --list is required")

    try:
        source_uuid = UUID(args.source_id)
    except ValueError as e:
        parser.error(f"invalid UUID for --source-id: {e}")

    asyncio.run(run(source_uuid, args.force))


if __name__ == "__main__":
    main()
