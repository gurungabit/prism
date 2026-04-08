#!/usr/bin/env python3
import sys
import time

from opensearchpy import OpenSearch

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "backend")
)

from src.config import settings
from src.ingestion.indexer import SEARCH_PIPELINE, INDEX_MAPPING


def wait_for_opensearch(client: OpenSearch, max_retries: int = 30) -> None:
    for attempt in range(max_retries):
        try:
            info = client.info()
            print(
                f"OpenSearch connected: {info['version']['distribution']} {info['version']['number']}"
            )
            return
        except Exception:
            print(f"Waiting for OpenSearch... ({attempt + 1}/{max_retries})")
            time.sleep(2)
    raise RuntimeError("OpenSearch not available")


def setup():
    client = OpenSearch(
        hosts=[settings.opensearch_url], use_ssl=False, verify_certs=False
    )
    wait_for_opensearch(client)

    index_name = settings.opensearch_index

    if client.indices.exists(index=index_name):
        print(f"Index already exists: {index_name}")
    else:
        print(f"Creating index: {index_name}")
        client.indices.create(index=index_name, body=INDEX_MAPPING)

    pipeline_name = "hybrid-search-pipeline"
    print(f"Creating search pipeline: {pipeline_name}")
    client.http.put(f"/_search/pipeline/{pipeline_name}", body=SEARCH_PIPELINE)

    client.indices.put_settings(
        index=index_name,
        body={"index.search.default_pipeline": pipeline_name},
    )

    print("OpenSearch setup complete")


if __name__ == "__main__":
    setup()
