import pytest
from src.ingestion.parser import parse_document, detect_doc_type, _parse_json, _parse_csv, _parse_html
from src.models.document import DocumentRef, DocumentMetadata, RawDocument


def _make_doc(content: str, file_type: str = ".md", path: str = "test/doc.md") -> RawDocument:
    return RawDocument(
        ref=DocumentRef(source_platform="gitlab", source_path=path, file_type=file_type),
        content=content,
        metadata=DocumentMetadata(title="Test"),
    )


def test_parse_markdown():
    doc = _make_doc("# Title\n\nSome content here")
    result = parse_document(doc)
    assert "Title" in result
    assert "content" in result


def test_parse_json_issue():
    json_content = '{"title": "Fix bug", "body": "The auth service has a bug", "labels": ["bug"], "state": "open"}'
    doc = _make_doc(json_content, file_type=".json", path="issues/issue-1.json")
    result = parse_document(doc)
    assert "Fix bug" in result
    assert "auth service" in result
    assert "bug" in result


def test_parse_csv():
    csv_content = "Service,Team,Status\nauth-service,Platform,active\npayment-service,Payments,active"
    result = _parse_csv(csv_content)
    assert "auth-service" in result
    assert "Platform" in result


def test_parse_html():
    html_content = "<html><body><h1>Title</h1><p>Content here</p><script>alert('x')</script></body></html>"
    result = _parse_html(html_content)
    assert "Title" in result
    assert "Content" in result
    assert "alert" not in result


def test_detect_doc_type_wiki():
    assert detect_doc_type("gitlab/team/wiki/guide.md", "content") == "wiki"


def test_detect_doc_type_readme():
    assert detect_doc_type("gitlab/service/README.md", "content") == "readme"


def test_detect_doc_type_runbook():
    assert detect_doc_type("gitlab/team/runbook.md", "content") == "runbook"


def test_detect_doc_type_incident():
    assert detect_doc_type("notes/incident-report.md", "content") == "incident_report"


def test_detect_doc_type_spreadsheet():
    assert detect_doc_type("data/services.xlsx", "content") == "spreadsheet"


def test_detect_doc_type_unknown():
    assert detect_doc_type("random/file.txt", "some random content") == "unknown"


def test_detect_doc_type_from_content():
    assert detect_doc_type("docs/report.md", "This incident occurred at 3am") == "incident_report"
