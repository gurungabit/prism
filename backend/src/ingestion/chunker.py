from __future__ import annotations

import re
import uuid

from src.models.chunk import Chunk, ChunkMetadata
from src.models.document import RawDocument
from src.ingestion.parser import detect_doc_type


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
APPROX_CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50


def chunk_document(
    document_id: str,
    parsed_content: str,
    raw_doc: RawDocument,
    chunk_size_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    if not parsed_content.strip():
        return []

    doc_type = detect_doc_type(raw_doc.ref.source_path, parsed_content)
    sections = _split_by_headings(parsed_content)
    chunk_size_chars = chunk_size_tokens * APPROX_CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * APPROX_CHARS_PER_TOKEN

    all_chunks: list[Chunk] = []

    for section_heading, section_content in sections:
        paragraphs = _split_paragraphs(section_content)
        section_chunks = _merge_paragraphs_into_chunks(paragraphs, chunk_size_chars, overlap_chars)

        for chunk_text in section_chunks:
            if not chunk_text.strip():
                continue

            team_hint, service_hint = _extract_hints(chunk_text, raw_doc.ref.source_path)

            all_chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=chunk_text.strip(),
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
