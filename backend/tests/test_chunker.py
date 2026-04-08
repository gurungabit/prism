import pytest
from src.ingestion.chunker import chunk_document, _split_by_headings, _split_paragraphs
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


def test_chunk_short_content():
    doc = _make_doc("Short text")
    chunks = chunk_document("doc-1", "Short text", doc)
    assert len(chunks) == 1
    assert chunks[0].content == "Short text"
    assert chunks[0].document_id == "doc-1"


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
