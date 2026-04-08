from __future__ import annotations

from datasketch import MinHash, MinHashLSH

from src.config import settings
from src.observability.logging import get_logger

log = get_logger("deduplicator")


class ChunkDeduplicator:
    def __init__(
        self,
        threshold: float = settings.dedup_threshold,
        num_perm: int = settings.dedup_num_perm,
    ) -> None:
        self.threshold = threshold
        self.num_perm = num_perm
        self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._minhashes: dict[str, MinHash] = {}

    def _compute_minhash(self, text: str) -> MinHash:
        mh = MinHash(num_perm=self.num_perm)
        words = text.lower().split()
        for word in words:
            mh.update(word.encode("utf-8"))
        return mh

    def check_duplicate(self, chunk_id: str, content: str) -> str | None:
        mh = self._compute_minhash(content)

        try:
            duplicates = self.lsh.query(mh)
        except ValueError:
            duplicates = []

        if duplicates:
            canonical = duplicates[0]
            log.debug("near_duplicate_found", chunk_id=chunk_id, canonical=canonical)
            return canonical

        try:
            self.lsh.insert(chunk_id, mh)
            self._minhashes[chunk_id] = mh
        except ValueError:
            pass

        return None

    def reset(self) -> None:
        self.lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        self._minhashes.clear()
