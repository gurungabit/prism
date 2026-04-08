import pytest
from src.ingestion.deduplicator import ChunkDeduplicator


def test_first_chunk_not_duplicate():
    dedup = ChunkDeduplicator(threshold=0.8, num_perm=128)
    result = dedup.check_duplicate("chunk-1", "This is a unique document about authentication")
    assert result is None


def test_identical_text_is_duplicate():
    dedup = ChunkDeduplicator(threshold=0.8, num_perm=128)
    text = "This is a document about authentication and security measures in the platform"
    dedup.check_duplicate("chunk-1", text)
    result = dedup.check_duplicate("chunk-2", text)
    assert result == "chunk-1"


def test_near_duplicate_detected():
    dedup = ChunkDeduplicator(threshold=0.5, num_perm=128)
    text1 = (
        "The authentication service handles user login and password verification for all platform users in production"
    )
    text2 = "The authentication service handles user login and password verification for all platform users in staging"
    dedup.check_duplicate("chunk-1", text1)
    result = dedup.check_duplicate("chunk-2", text2)
    assert result == "chunk-1"


def test_different_text_not_duplicate():
    dedup = ChunkDeduplicator(threshold=0.8, num_perm=128)
    text1 = "The payment processor handles credit card transactions and refunds"
    text2 = "The deployment pipeline uses Kubernetes for container orchestration"
    dedup.check_duplicate("chunk-1", text1)
    result = dedup.check_duplicate("chunk-2", text2)
    assert result is None


def test_reset_clears_state():
    dedup = ChunkDeduplicator(threshold=0.8, num_perm=128)
    text = "Repeated content about the auth service"
    dedup.check_duplicate("chunk-1", text)
    dedup.reset()
    result = dedup.check_duplicate("chunk-2", text)
    assert result is None
