import json
import tempfile
from pathlib import Path

import pytest
from src.connectors.gitlab import GitLabConnector
from src.connectors.excel import ExcelConnector
from src.connectors.sharepoint import SharePointConnector
from src.connectors.onenote import OneNoteConnector


@pytest.fixture
def gitlab_dir(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "team" / "service"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("# Service\n\nDescription")
    wiki_dir = repo_dir / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "guide.md").write_text("# Guide\n\nHow to use")
    issues_dir = repo_dir / "issues"
    issues_dir.mkdir()
    (issues_dir / "issue-1.json").write_text(
        json.dumps(
            {
                "title": "Fix bug",
                "body": "There is a bug",
                "labels": ["bug"],
                "state": "open",
            }
        )
    )
    return tmp_path


def test_gitlab_list_documents(gitlab_dir: Path):
    connector = GitLabConnector(gitlab_dir)
    refs = connector.list_documents()
    paths = [r.source_path for r in refs]
    assert any("README.md" in p for p in paths)
    assert any("guide.md" in p for p in paths)
    assert any("issue-1.json" in p for p in paths)


def test_gitlab_fetch_readme(gitlab_dir: Path):
    connector = GitLabConnector(gitlab_dir)
    refs = connector.list_documents()
    readme_ref = next(r for r in refs if "README.md" in r.source_path)
    doc = connector.fetch_document(readme_ref)
    assert "Service" in doc.metadata.title
    assert "Description" in doc.content


def test_gitlab_fetch_json_issue(gitlab_dir: Path):
    connector = GitLabConnector(gitlab_dir)
    refs = connector.list_documents()
    issue_ref = next(r for r in refs if "issue-1.json" in r.source_path)
    doc = connector.fetch_document(issue_ref)
    assert doc.metadata.title == "Fix bug"
    assert doc.metadata.labels == ["bug"]


@pytest.fixture
def sharepoint_dir(tmp_path: Path) -> Path:
    site_dir = tmp_path / "team-site"
    site_dir.mkdir()
    (site_dir / "document.md").write_text("# SharePoint Doc\n\nContent")
    return tmp_path


def test_sharepoint_list_documents(sharepoint_dir: Path):
    connector = SharePointConnector(sharepoint_dir)
    refs = connector.list_documents()
    assert len(refs) == 1
    assert refs[0].source_platform == "sharepoint"


@pytest.fixture
def onenote_dir(tmp_path: Path) -> Path:
    section_dir = tmp_path / "notebook" / "section"
    section_dir.mkdir(parents=True)
    (section_dir / "page.html").write_text("<h1>Notes</h1><p>Content</p>")
    return tmp_path


def test_onenote_list_and_fetch(onenote_dir: Path):
    connector = OneNoteConnector(onenote_dir)
    refs = connector.list_documents()
    assert len(refs) == 1
    doc = connector.fetch_document(refs[0])
    assert "Notes" in doc.content or "Content" in doc.content
    assert doc.metadata.extra.get("section") == "section"
