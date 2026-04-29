from __future__ import annotations

import re
import uuid
from typing import Literal

from src.ingestion.parser import detect_doc_type
from src.models.chunk import Chunk, ChunkMetadata
from src.models.document import RawDocument
from src.observability.logging import get_logger


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.MULTILINE)
APPROX_CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50
DEFAULT_SEMANTIC_MIN_CHUNK_TOKENS = 120
DEFAULT_SEMANTIC_BREAKPOINT_PERCENTILE = 80.0
DEFAULT_SEMANTIC_BREAKPOINT_THRESHOLD = 0.2
MIN_SEMANTIC_DISTANCE_SPREAD = 0.05

ChunkingStrategy = Literal["semantic", "structural"]

log = get_logger("chunker")


def chunk_document(
    document_id: str,
    parsed_content: str,
    raw_doc: RawDocument,
    chunk_size_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    chunking_strategy: ChunkingStrategy = "semantic",
    semantic_min_chunk_tokens: int = DEFAULT_SEMANTIC_MIN_CHUNK_TOKENS,
    semantic_breakpoint_percentile: float = DEFAULT_SEMANTIC_BREAKPOINT_PERCENTILE,
    semantic_breakpoint_threshold: float = DEFAULT_SEMANTIC_BREAKPOINT_THRESHOLD,
) -> list[Chunk]:
    if not parsed_content.strip():
        return []

    doc_type = detect_doc_type(raw_doc.ref.source_path, parsed_content)
    sections = _split_by_headings(parsed_content)
    chunk_size_chars = chunk_size_tokens * APPROX_CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * APPROX_CHARS_PER_TOKEN
    semantic_min_chunk_chars = semantic_min_chunk_tokens * APPROX_CHARS_PER_TOKEN

    document_title = raw_doc.metadata.title or ""

    all_chunks: list[Chunk] = []

    for section_heading, section_content in sections:
        section_chunks = _chunk_section(
            section_content,
            chunk_size_chars,
            overlap_chars,
            chunking_strategy=chunking_strategy,
            semantic_min_chunk_chars=semantic_min_chunk_chars,
            semantic_breakpoint_percentile=semantic_breakpoint_percentile,
            semantic_breakpoint_threshold=semantic_breakpoint_threshold,
        )

        for chunk_text in section_chunks:
            stripped = chunk_text.strip()
            if not stripped:
                continue

            # Inline the heading + title so embedding and BM25 see them
            # alongside the body, not just on metadata.
            context_line = _build_context_line(document_title, section_heading)
            content_with_context = (
                f"{context_line}\n\n{stripped}" if context_line else stripped
            )

            team_hint, service_hint = _extract_hints(content_with_context, raw_doc.ref.source_path)

            all_chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=content_with_context,
                    metadata=ChunkMetadata(
                        source_platform=raw_doc.ref.source_platform,
                        source_path=raw_doc.ref.source_path,
                        source_url=raw_doc.metadata.source_url,
                        document_title=raw_doc.metadata.title,
                        section_heading=section_heading,
                        team_hint=team_hint,
                        service_hint=service_hint,
                        doc_type=doc_type,
                        last_modified=raw_doc.metadata.last_modified,
                        author=raw_doc.metadata.author,
                    ),
                )
            )

    for idx, chunk in enumerate(all_chunks):
        chunk.metadata.chunk_index = idx
        chunk.metadata.total_chunks = len(all_chunks)

    return all_chunks


def _build_context_line(document_title: str, section_heading: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for part in (document_title, section_heading):
        cleaned = (part or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(cleaned)
    if not parts:
        return ""
    return f"[{' > '.join(parts)}]"


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [("", text)]

    sections = []

    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(("", preamble))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections.append((heading, content))

    return sections if sections else [("", text)]


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _chunk_section(
    section_content: str,
    chunk_size_chars: int,
    overlap_chars: int,
    *,
    chunking_strategy: ChunkingStrategy,
    semantic_min_chunk_chars: int,
    semantic_breakpoint_percentile: float,
    semantic_breakpoint_threshold: float,
) -> list[str]:
    paragraphs = _split_paragraphs(section_content)
    if chunking_strategy != "semantic" or _is_list_block(section_content):
        return _merge_paragraphs_into_chunks(paragraphs, chunk_size_chars, overlap_chars)

    try:
        return _merge_semantic_units_into_chunks(
            section_content,
            chunk_size_chars,
            overlap_chars,
            semantic_min_chunk_chars=semantic_min_chunk_chars,
            semantic_breakpoint_percentile=semantic_breakpoint_percentile,
            semantic_breakpoint_threshold=semantic_breakpoint_threshold,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("semantic_chunking_failed", error=str(e)[:200])
        return _merge_paragraphs_into_chunks(paragraphs, chunk_size_chars, overlap_chars)


def _merge_semantic_units_into_chunks(
    section_content: str,
    chunk_size_chars: int,
    overlap_chars: int,
    *,
    semantic_min_chunk_chars: int,
    semantic_breakpoint_percentile: float,
    semantic_breakpoint_threshold: float,
) -> list[str]:
    units = _split_semantic_units(section_content, chunk_size_chars)
    if len(units) < 2:
        return _merge_paragraphs_into_chunks(_split_paragraphs(section_content), chunk_size_chars, overlap_chars)

    embeddings = _embed_semantic_units(units)
    distances = _adjacent_cosine_distances(embeddings)
    breakpoints = _semantic_breakpoint_indexes(
        distances,
        percentile=semantic_breakpoint_percentile,
        minimum_distance=semantic_breakpoint_threshold,
    )
    suffix_lengths = _suffix_char_lengths(units)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for idx, unit in enumerate(units):
        unit_len = len(unit)
        if current:
            would_exceed = current_len + unit_len + 2 > chunk_size_chars
            semantic_break = (
                idx in breakpoints
                and current_len >= semantic_min_chunk_chars
                and suffix_lengths[idx] >= semantic_min_chunk_chars
            )
            if would_exceed or semantic_break:
                chunks.append("\n\n".join(current))
                current = _overlap_units(current, overlap_chars) if would_exceed else []
                current_len = _joined_len(current)
                if current and current_len + unit_len + 2 > chunk_size_chars:
                    current = []
                    current_len = 0

        current.append(unit)
        current_len += unit_len + (2 if current_len else 0)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _split_semantic_units(section_content: str, chunk_size_chars: int) -> list[str]:
    units: list[str] = []
    for paragraph in _split_paragraphs(section_content):
        if len(paragraph) <= chunk_size_chars:
            units.append(paragraph)
            continue
        units.extend(_split_long_paragraph(paragraph, chunk_size_chars, overlap=0))
    return units


def _embed_semantic_units(units: list[str]) -> list[list[float]]:
    from src.ingestion.embedder import get_model

    model = get_model()
    embeddings = model.encode(
        units,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    out: list[list[float]] = []
    for embedding in embeddings:
        values = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        out.append([float(value) for value in values])
    return out


def _adjacent_cosine_distances(embeddings: list[list[float]]) -> list[float]:
    distances: list[float] = []
    for left, right in zip(embeddings, embeddings[1:]):
        similarity = sum(a * b for a, b in zip(left, right))
        distances.append(1.0 - similarity)
    return distances


def _semantic_breakpoint_indexes(
    distances: list[float],
    *,
    percentile: float,
    minimum_distance: float,
) -> set[int]:
    if not distances:
        return set()

    if len(distances) > 1 and max(distances) - min(distances) < MIN_SEMANTIC_DISTANCE_SPREAD:
        return set()

    cutoff = max(minimum_distance, _percentile(distances, percentile))
    return {idx + 1 for idx, distance in enumerate(distances) if distance >= cutoff}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    clamped = min(100.0, max(0.0, percentile))
    if len(ordered) == 1:
        return ordered[0]

    rank = (clamped / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _suffix_char_lengths(units: list[str]) -> list[int]:
    lengths = [0] * len(units)
    running = 0
    for idx in range(len(units) - 1, -1, -1):
        running += len(units[idx]) + (2 if running else 0)
        lengths[idx] = running
    return lengths


def _overlap_units(units: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0:
        return []

    overlap: list[str] = []
    total = 0
    for unit in reversed(units):
        next_len = len(unit) + (2 if overlap else 0)
        if overlap and total + next_len > overlap_chars:
            break
        overlap.insert(0, unit)
        total += next_len
        if total >= overlap_chars:
            break
    return overlap


def _joined_len(units: list[str]) -> int:
    if not units:
        return 0
    return sum(len(unit) for unit in units) + 2 * (len(units) - 1)


def _merge_paragraphs_into_chunks(
    paragraphs: list[str],
    chunk_size_chars: int,
    overlap_chars: int,
) -> list[str]:
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)

        if para_len > chunk_size_chars:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_len = 0

            for sub_chunk in _split_long_paragraph(para, chunk_size_chars, overlap_chars):
                chunks.append(sub_chunk)
            continue

        if current_len + para_len + 2 > chunk_size_chars and current_parts:
            chunks.append("\n\n".join(current_parts))

            overlap_text = "\n\n".join(current_parts)
            if len(overlap_text) > overlap_chars:
                overlap_text = overlap_text[-overlap_chars:]

            current_parts = [overlap_text] if overlap_chars > 0 else []
            current_len = len(overlap_text) if overlap_chars > 0 else 0

        current_parts.append(para)
        current_len += para_len + 2

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def _split_long_paragraph(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0 or not text:
        return [text] if text else []

    # Bullet/numbered lists have no sentence-ending periods, so the
    # generic ``rfind(". ")`` splitter below would slice mid-line.
    if _is_list_block(text):
        return _split_list_block(text, chunk_size, overlap)

    chunks: list[str] = []
    start = 0
    n = len(text)
    min_step = max(1, chunk_size - overlap)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            break_point = text.rfind(". ", start + min_step, end)
            if break_point != -1:
                end = break_point + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        next_start = end - overlap if overlap > 0 else end
        start = max(start + min_step, next_start)
    return chunks


def _is_list_block(text: str) -> bool:
    # ``>= 50%`` of non-empty lines marker-led tolerates list intros
    # like "Key components:" sharing the paragraph with their items.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    list_lines = sum(1 for ln in lines if LIST_ITEM_PATTERN.match(ln))
    return list_lines * 2 >= len(lines)


def _split_list_block(text: str, chunk_size: int, overlap: int) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if LIST_ITEM_PATTERN.match(line) and current:
            items.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        items.append("\n".join(current))

    if not items:
        return [text]

    chunks: list[str] = []
    bucket: list[str] = []
    bucket_len = 0
    for item in items:
        item_len = len(item)
        if bucket and bucket_len + item_len + 1 > chunk_size:
            chunks.append("\n".join(bucket))
            if overlap > 0 and bucket:
                tail = bucket[-1]
                bucket = [tail]
                bucket_len = len(tail)
            else:
                bucket = []
                bucket_len = 0
        bucket.append(item)
        bucket_len += item_len + 1

    if bucket:
        chunks.append("\n".join(bucket))

    return chunks


def _extract_hints(content: str, source_path: str) -> tuple[str, str]:
    team_hint = ""
    service_hint = ""

    path_parts = source_path.lower().split("/")
    for part in path_parts:
        if "team" in part:
            team_hint = part.replace("-", " ").replace("_", " ").strip()
            break

    service_patterns = re.findall(r"(\w+[-_]service|\w+[-_]api|\w+[-_]gateway)", content.lower())
    if service_patterns:
        service_hint = service_patterns[0].replace("_", "-")

    return team_hint, service_hint
