#!/usr/bin/env python3
import argparse
import asyncio
import sys

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "backend")
)

from src.ingestion.pipeline import IngestionPipeline
from src.observability.logging import setup_logging


async def run_ingestion(platform: str | None, force: bool, data_dir: str | None):
    setup_logging()
    pipeline = await IngestionPipeline.create()

    try:
        if platform:
            print(f"Ingesting platform: {platform} (force={force})")
            stats = await pipeline.ingest_platform(
                platform, data_dir=data_dir, force=force
            )
        else:
            print(f"Ingesting all platforms (force={force})")
            stats = await pipeline.ingest_all(data_dir=data_dir, force=force)

        print(f"\nIngestion complete:")
        print(f"  Total documents: {stats['total']}")
        print(f"  Indexed: {stats['indexed']}")
        print(f"  Skipped (unchanged): {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")

        if "platforms" in stats:
            for p in stats["platforms"]:
                print(f"\n  {p['platform']}:")
                print(
                    f"    Total: {p['total']}, Indexed: {p['indexed']}, Skipped: {p['skipped']}, Failed: {p['failed']}"
                )

    finally:
        await pipeline.close()


def main():
    parser = argparse.ArgumentParser(description="PRISM Document Ingestion")
    parser.add_argument(
        "--platform",
        type=str,
        help="Specific platform to ingest (gitlab, sharepoint, excel, onenote)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force full re-index (ignore content hashes)",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None, help="Override data directory"
    )
    args = parser.parse_args()

    asyncio.run(run_ingestion(args.platform, args.force, args.data_dir))


if __name__ == "__main__":
    main()
