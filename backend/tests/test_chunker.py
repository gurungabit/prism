import pytest
from src.ingestion.chunker import (
    _split_by_headings,
    _split_list_block,
    _split_paragraphs,
    chunk_document,
)
from src.models.document import DocumentRef, DocumentMetadata, RawDocument


def _make_doc(content: str, path: str = "test/doc.md") -> RawDocument:
    return RawDocument(
        ref=DocumentRef(source_platform="gitlab", source_path=path, file_type=".md"),
        content=content,
        metadata=DocumentMetadata(title="Test Doc"),
    )


def test_chunk_empty_content():
    doc = _make_doc("")
    chunks = chunk_document("doc-1", "", doc)
    assert chunks == []


def test_chunk_short_content_has_title_prefix():
    """A bare doc body still gets the title prepended so embedding +
    BM25 see the document title alongside the body."""
    doc = _make_doc("Short text")
    chunks = chunk_document("doc-1", "Short text", doc)
    assert len(chunks) == 1
    assert chunks[0].content == "[Test Doc]\n\nShort text"
    assert chunks[0].document_id == "doc-1"


def test_chunk_section_gets_title_and_heading_prefix():
    """When the doc has a heading, the chunk content carries
    ``[Title > Heading]`` so retrieval can match queries that share
    vocabulary with the heading rather than the body."""
    body = "# External Service Integrations\n\n- AWS SNS\n- Stripe\n- DataDog"
    doc = _make_doc(body)
    doc.metadata.title = "nbus-aws"
    chunks = chunk_document("doc-1", body, doc)
    assert len(chunks) == 1
    assert chunks[0].content.startswith(
        "[nbus-aws > External Service Integrations]\n\n"
    )
    assert "AWS SNS" in chunks[0].content


def test_chunk_preserves_metadata():
    doc = _make_doc("Content here", path="gitlab/team/service/wiki/guide.md")
    doc.metadata.title = "Guide"
    doc.metadata.author = "alice"
    chunks = chunk_document("doc-1", "Content here", doc)
    assert len(chunks) == 1
    assert chunks[0].metadata.source_platform == "gitlab"
    assert chunks[0].metadata.source_path == "gitlab/team/service/wiki/guide.md"
    assert chunks[0].metadata.document_title == "Guide"
    assert chunks[0].metadata.author == "alice"
    assert chunks[0].metadata.doc_type == "wiki"


def test_chunk_indexes():
    content = "\n\n".join([f"Paragraph {i} " * 200 for i in range(5)])
    doc = _make_doc(content)
    chunks = chunk_document("doc-1", content, doc, chunk_size_tokens=100)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.metadata.chunk_index == i
        assert chunk.metadata.total_chunks == len(chunks)


def test_split_by_headings():
    text = "Preamble\n\n# Section 1\n\nContent 1\n\n## Section 2\n\nContent 2"
    sections = _split_by_headings(text)
    assert len(sections) == 3
    assert sections[0][0] == ""
    assert "Preamble" in sections[0][1]
    assert sections[1][0] == "Section 1"
    assert sections[2][0] == "Section 2"


def test_split_by_headings_no_headings():
    text = "Just plain text\n\nWith paragraphs"
    sections = _split_by_headings(text)
    assert len(sections) == 1
    assert sections[0][0] == ""


def test_split_paragraphs():
    text = "Para 1\n\nPara 2\n\nPara 3"
    paragraphs = _split_paragraphs(text)
    assert len(paragraphs) == 3


def test_chunk_detects_service_hint():
    doc = _make_doc("The auth-service handles authentication", path="test/doc.md")
    chunks = chunk_document("doc-1", "The auth-service handles authentication", doc)
    assert len(chunks) == 1
    assert chunks[0].metadata.service_hint == "auth-service"


def test_split_list_block_keeps_items_intact():
    """Bullet lists must split at item boundaries, not mid-line. The
    old splitter used ``rfind('. ')`` which produced garbled chunks
    for lists (no periods to split on)."""
    items = [f"- Service-{i}: a short description for item {i}" for i in range(1, 21)]
    text = "\n".join(items)
    pieces = _split_list_block(text, chunk_size=200, overlap=0)
    assert len(pieces) > 1
    # Every piece must start with a list marker -- proof we never split
    # mid-item.
    for piece in pieces:
        assert piece.lstrip().startswith("-")
    # And every original item appears intact in some piece.
    for item in items:
        assert any(item in p for p in pieces)


def test_chunk_long_list_keeps_items_atomic():
    """End-to-end: a long bullet list inside a section produces chunks
    where every line is still a recognizable list item."""
    items = [f"- External-Service-{i}" for i in range(1, 50)]
    body = "# External Service Integrations\n\n" + "\n".join(items)
    doc = _make_doc(body)
    chunks = chunk_document("doc-1", body, doc, chunk_size_tokens=50)
    # The list is too long to fit one chunk, so we expect multiple --
    # but each must contain only whole items.
    assert len(chunks) > 1
    for chunk in chunks:
        # Drop the prefix line; everything else should be list items.
        body_lines = [
            ln
            for ln in chunk.content.splitlines()
            if ln.strip() and not ln.startswith("[")
        ]
        for ln in body_lines:
            assert ln.lstrip().startswith("-")
