"""Connector tests.

The GitLab connector is now API-based, so we mock httpx responses to exercise
the URL-shape translation + tree/file fetching. File-based connectors
(SharePoint, Excel, OneNote) still walk the filesystem, so those tests just
pass a ``SourceConfig`` with a ``path``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from src.config import settings
from src.connectors.base import LocalPathRejected, SourceConfig, resolve_local_path
from src.connectors.excel import ExcelConnector
from src.connectors.gitlab import GitLabConnector, _is_knowledge_path, _next_page_url
from src.connectors.onenote import OneNoteConnector
from src.connectors.sharepoint import SharePointConnector


# ---------- shared helpers ----------


def _build_mock_transport(routes: dict[str, httpx.Response | list[httpx.Response]]) -> httpx.MockTransport:
    """Tiny mock transport keyed on request path.

    Each key is a substring match against the request URL; first match wins.
    Values can be a single response or a list of responses consumed in order
    (so list_documents pagination can be exercised).
    """
    remaining: dict[str, list[httpx.Response]] = {
        k: list(v) if isinstance(v, list) else [v] for k, v in routes.items()
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, responses in remaining.items():
            if key in url and responses:
                return responses.pop(0)
        return httpx.Response(404, json={"message": "Not Found", "url": url})

    return httpx.MockTransport(handler)


# ---------- GitLab connector ----------


def test_gitlab_knowledge_path_matcher():
    assert _is_knowledge_path("README.md") is True
    assert _is_knowledge_path("readme.rst") is True
    assert _is_knowledge_path("CODEOWNERS") is True
    assert _is_knowledge_path("docs/setup.md") is True
    assert _is_knowledge_path("runbooks/on-call.md") is True
    assert _is_knowledge_path("architecture/overview.md") is True
    # Not knowledge: source files, CI config, nested non-docs.
    assert _is_knowledge_path("src/main.py") is False
    assert _is_knowledge_path(".gitlab-ci.yml") is False
    assert _is_knowledge_path("docs/example.pdf") is False


def test_gitlab_parse_next_page_url():
    # GitLab sends absolute URLs in Link headers; we pass them through as-is
    # because httpx's Client accepts absolute URLs even when base_url is set.
    request = httpx.Request("GET", "https://gitlab.example/api/v4/projects")
    response = httpx.Response(
        200,
        request=request,
        headers={
            "link": (
                '<https://gitlab.example/api/v4/projects?page=1>; rel="first", '
                '<https://gitlab.example/api/v4/projects?page=2>; rel="next"'
            )
        },
    )
    assert _next_page_url(response) == "https://gitlab.example/api/v4/projects?page=2"

    # No rel=next → None.
    assert (
        _next_page_url(
            httpx.Response(
                200,
                request=request,
                headers={"link": '<https://gitlab.example/api/v4/projects?page=1>; rel="first"'},
            )
        )
        is None
    )
    # No Link header → None.
    assert _next_page_url(httpx.Response(200, request=request)) is None


def test_gitlab_list_single_project_documents():
    project_payload = {
        "id": 99,
        "name": "api-gateway",
        "path_with_namespace": "platform-team/api-gateway",
        "web_url": "https://gitlab.example/platform-team/api-gateway",
        "default_branch": "main",
        "description": "Edge service",
        "topics": ["platform", "gateway"],
        "last_activity_at": "2024-05-01T10:00:00Z",
    }
    tree_payload = [
        {"type": "blob", "path": "README.md"},
        {"type": "blob", "path": "docs/setup.md"},
        {"type": "blob", "path": "docs/architecture/overview.md"},
        {"type": "blob", "path": "src/main.py"},  # should be filtered out
        {"type": "tree", "path": "src"},
    ]

    routes = {
        "projects/platform-team%2Fapi-gateway": httpx.Response(200, json=project_payload),
        "repository/tree": httpx.Response(200, json=tree_payload),
    }

    source = SourceConfig(
        kind="gitlab",
        name="gateway",
        config={"project_path": "platform-team/api-gateway"},
        token="glpat-test",
    )
    connector = GitLabConnector(source)
    # Swap the httpx client with one whose transport serves our canned responses.
    connector._client = httpx.Client(
        base_url="https://gitlab.example/api/v4",
        headers={"PRIVATE-TOKEN": "glpat-test"},
        transport=_build_mock_transport(routes),
    )

    refs = connector.list_documents()
    paths = [r.source_path for r in refs]

    # Expect README + two docs files, not src/main.py.
    assert any("README.md" in p for p in paths)
    assert any("docs/setup.md" in p for p in paths)
    assert any("docs/architecture/overview.md" in p for p in paths)
    assert not any("src/main.py" in p for p in paths)
    # Namespaced path shape: <project>@<ref>:<inner>
    for p in paths:
        assert "@main:" in p
        assert p.startswith("platform-team/api-gateway@")

    connector.close()


def test_gitlab_fetch_document_populates_metadata():
    project_payload = {
        "id": 7,
        "name": "auth-service",
        "path_with_namespace": "platform-team/auth-service",
        "web_url": "https://gitlab.example/platform-team/auth-service",
        "default_branch": "main",
        "topics": [],
        "description": "Handles auth",
        "last_activity_at": "2024-05-02T11:00:00Z",
    }
    readme_content = "# Auth Service\n\nHandles tokens."
    commit_payload = [{"committed_date": "2024-04-30T12:00:00Z"}]

    routes = {
        "projects/platform-team%2Fauth-service": httpx.Response(200, json=project_payload),
        "/files/": httpx.Response(200, content=readme_content.encode("utf-8")),
        "/commits": httpx.Response(200, json=commit_payload),
    }

    source = SourceConfig(
        kind="gitlab",
        name="auth",
        config={"project_path": "platform-team/auth-service", "ref": "main"},
        token="glpat-test",
    )
    connector = GitLabConnector(source)
    connector._client = httpx.Client(
        base_url="https://gitlab.example/api/v4",
        headers={"PRIVATE-TOKEN": "glpat-test"},
        transport=_build_mock_transport(routes),
    )

    # Pre-populate project cache the way list_documents would.
    connector._project_cache[project_payload["path_with_namespace"]] = project_payload

    from src.models.document import DocumentRef

    ref = DocumentRef(
        source_platform="gitlab",
        source_path="platform-team/auth-service@main:README.md",
        file_type=".md",
    )
    doc = connector.fetch_document(ref)

    assert "Auth Service" in doc.metadata.title
    assert doc.metadata.source_url.startswith("https://gitlab.example/platform-team/auth-service/-/blob/main/")
    assert doc.metadata.extra["gitlab_project_id"] == 7
    assert doc.metadata.extra["gitlab_project_path"] == "platform-team/auth-service"
    assert doc.metadata.last_modified is not None

    connector.close()


def test_gitlab_lists_wiki_pages_alongside_files():
    project_payload = {
        "id": 42,
        "name": "billing",
        "path_with_namespace": "platform-team/billing",
        "web_url": "https://gitlab.example/platform-team/billing",
        "default_branch": "main",
        "description": "",
        "topics": [],
        "last_activity_at": "2024-06-01T00:00:00Z",
        "wiki_enabled": True,
    }
    tree_payload = [{"type": "blob", "path": "README.md"}]
    wiki_list_payload = [
        {"slug": "home", "title": "Home", "format": "markdown"},
        {"slug": "architecture/overview", "title": "Architecture Overview", "format": "markdown"},
    ]

    routes = {
        "projects/platform-team%2Fbilling": httpx.Response(200, json=project_payload),
        "repository/tree": httpx.Response(200, json=tree_payload),
        "/wikis": httpx.Response(200, json=wiki_list_payload),
    }

    source = SourceConfig(
        kind="gitlab",
        name="billing",
        config={"project_path": "platform-team/billing"},
        token="glpat-test",
    )
    connector = GitLabConnector(source)
    connector._client = httpx.Client(
        base_url="https://gitlab.example/api/v4",
        headers={"PRIVATE-TOKEN": "glpat-test"},
        transport=_build_mock_transport(routes),
    )

    refs = connector.list_documents()
    paths = [r.source_path for r in refs]

    assert any(p.endswith("@main:README.md") for p in paths)
    assert any("@__wiki__:wiki/home" in p for p in paths)
    assert any("@__wiki__:wiki/architecture/overview" in p for p in paths)

    connector.close()


def test_gitlab_fetch_wiki_page_uses_wiki_endpoint():
    project_payload = {
        "id": 42,
        "name": "billing",
        "path_with_namespace": "platform-team/billing",
        "web_url": "https://gitlab.example/platform-team/billing",
        "default_branch": "main",
        "description": "",
        "topics": [],
        "last_activity_at": "2024-06-01T00:00:00Z",
    }
    wiki_page_payload = {
        "slug": "home",
        "title": "Billing Home",
        "format": "markdown",
        "content": "# Billing\n\nWelcome to the wiki.",
    }

    routes = {
        "/wikis/home": httpx.Response(200, json=wiki_page_payload),
    }

    source = SourceConfig(
        kind="gitlab",
        name="billing",
        config={"project_path": "platform-team/billing"},
        token="glpat-test",
    )
    connector = GitLabConnector(source)
    connector._client = httpx.Client(
        base_url="https://gitlab.example/api/v4",
        headers={"PRIVATE-TOKEN": "glpat-test"},
        transport=_build_mock_transport(routes),
    )
    connector._project_cache[project_payload["path_with_namespace"]] = project_payload

    from src.models.document import DocumentRef

    ref = DocumentRef(
        source_platform="gitlab",
        source_path="platform-team/billing@__wiki__:wiki/home",
        file_type=".md",
    )
    doc = connector.fetch_document(ref)

    assert doc.content.startswith("# Billing")
    assert doc.metadata.title == "Billing Home"
    assert doc.metadata.source_url == "https://gitlab.example/platform-team/billing/-/wikis/home"
    assert doc.metadata.extra["gitlab_wiki_slug"] == "home"
    assert doc.metadata.extra["gitlab_wiki_format"] == "markdown"

    connector.close()


def test_gitlab_wiki_disabled_via_config():
    project_payload = {
        "id": 42,
        "name": "billing",
        "path_with_namespace": "platform-team/billing",
        "web_url": "https://gitlab.example/platform-team/billing",
        "default_branch": "main",
        "topics": [],
        "description": "",
        "last_activity_at": "2024-06-01T00:00:00Z",
    }
    routes = {
        "projects/platform-team%2Fbilling": httpx.Response(200, json=project_payload),
        "repository/tree": httpx.Response(200, json=[{"type": "blob", "path": "README.md"}]),
    }

    source = SourceConfig(
        kind="gitlab",
        name="billing",
        config={"project_path": "platform-team/billing", "include_wiki": False},
        token="glpat-test",
    )
    connector = GitLabConnector(source)
    connector._client = httpx.Client(
        base_url="https://gitlab.example/api/v4",
        headers={"PRIVATE-TOKEN": "glpat-test"},
        transport=_build_mock_transport(routes),
    )

    refs = connector.list_documents()
    assert all("__wiki__" not in r.source_path for r in refs)

    connector.close()


def test_gitlab_search_projects_paginates():
    page1 = [
        {"id": 1, "name": "a", "path_with_namespace": "team/a", "web_url": "", "default_branch": "main"},
        {"id": 2, "name": "b", "path_with_namespace": "team/b", "web_url": "", "default_branch": "main"},
    ]
    page2 = [
        {"id": 3, "name": "c", "path_with_namespace": "team/c", "web_url": "", "default_branch": "main"},
    ]

    routes = {
        "page=1": httpx.Response(200, json=page1, headers={"x-next-page": "2"}),
        "page=2": httpx.Response(200, json=page2, headers={"x-next-page": ""}),
    }

    source = SourceConfig(
        kind="gitlab",
        name="picker",
        config={},
        token="glpat-test",
    )
    connector = GitLabConnector(source)
    connector._client = httpx.Client(
        base_url="https://gitlab.example/api/v4",
        headers={"PRIVATE-TOKEN": "glpat-test"},
        transport=_build_mock_transport(routes),
    )

    projects, has_more = connector.search_projects("team", page=1, per_page=2)
    assert [p["path_with_namespace"] for p in projects] == ["team/a", "team/b"]
    assert has_more is True

    projects, has_more = connector.search_projects("team", page=2, per_page=2)
    assert [p["path_with_namespace"] for p in projects] == ["team/c"]
    assert has_more is False

    connector.close()


def test_gitlab_missing_config_raises():
    source = SourceConfig(kind="gitlab", name="bad", config={}, token=None)
    connector = GitLabConnector(source)
    with pytest.raises(Exception):
        connector._resolve_projects()
    connector.close()


# ---------- SharePoint (file-based stub) ----------


@pytest.fixture
def sharepoint_dir(tmp_path: Path) -> Path:
    site_dir = tmp_path / "team-site"
    site_dir.mkdir()
    (site_dir / "document.md").write_text("# SharePoint Doc\n\nContent")
    return tmp_path


def test_sharepoint_list_documents(
    sharepoint_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    # File-based connectors run through ``resolve_local_path``; round 11
    # made the jail default-on, so a test fixture under pytest's
    # ``tmp_path`` (outside ``./data``) needs to either become the jail
    # or opt out via the escape hatch. Pointing the root *at* the
    # fixture is the more honest test setup.
    monkeypatch.setattr(settings, "local_source_root", str(sharepoint_dir))
    source = SourceConfig(
        kind="sharepoint",
        name="sp-local",
        config={"path": str(sharepoint_dir)},
    )
    connector = SharePointConnector(source)
    refs = connector.list_documents()
    assert len(refs) == 1
    assert refs[0].source_platform == "sharepoint"


# ---------- OneNote (file-based stub) ----------


@pytest.fixture
def onenote_dir(tmp_path: Path) -> Path:
    section_dir = tmp_path / "notebook" / "section"
    section_dir.mkdir(parents=True)
    (section_dir / "page.html").write_text("<h1>Notes</h1><p>Content</p>")
    return tmp_path


def test_onenote_list_and_fetch(
    onenote_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "local_source_root", str(onenote_dir))
    source = SourceConfig(
        kind="onenote",
        name="on-local",
        config={"path": str(onenote_dir)},
    )
    connector = OneNoteConnector(source)
    refs = connector.list_documents()
    assert len(refs) == 1
    doc = connector.fetch_document(refs[0])
    assert "Notes" in doc.content or "Content" in doc.content
    assert doc.metadata.extra.get("section") == "section"


# ---------- Excel (file-based stub) ----------


def test_excel_list_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "roster.csv").write_text("name,team\nalice,platform")
    monkeypatch.setattr(settings, "local_source_root", str(tmp_path))

    source = SourceConfig(
        kind="excel",
        name="excel-local",
        config={"path": str(tmp_path)},
    )
    connector = ExcelConnector(source)
    refs = connector.list_documents()
    assert len(refs) == 1
    assert refs[0].source_platform == "excel"


# ---------- resolve_local_path: rounds 10 + 11 hardening ----------
#
# Round 10 removed the ``.`` fallback and added an opt-in jail via the
# ``PRISM_LOCAL_SOURCE_ROOT`` env var. Round 11 made the jail
# default-on by reading ``settings.local_source_root`` (defaults to
# ``./data``) and adding a deliberate
# ``allow_unsandboxed_local_sources`` escape hatch. These tests pin
# all three layers: missing path is rejected, paths outside the jail
# (literal, ``..``, symlink-escaped) are rejected, and the escape
# hatch works for development workflows that need it.


def test_resolve_local_path_rejects_missing_path():
    src = SourceConfig(kind="excel", name="x", config={})
    with pytest.raises(LocalPathRejected, match="Missing 'path'"):
        resolve_local_path(src)


def test_resolve_local_path_rejects_blank_path():
    src = SourceConfig(kind="excel", name="x", config={"path": "   "})
    with pytest.raises(LocalPathRejected, match="Missing 'path'"):
        resolve_local_path(src)


def test_resolve_local_path_accepts_path_inside_jail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # ``settings`` is a module-level singleton -- patch the attribute
    # rather than the env var so the test sees the change without
    # re-importing the settings module.
    monkeypatch.setattr(settings, "local_source_root", str(tmp_path))
    monkeypatch.setattr(settings, "allow_unsandboxed_local_sources", False)
    inner = tmp_path / "team-docs"
    inner.mkdir()
    src = SourceConfig(kind="excel", name="x", config={"path": str(inner)})
    resolved = resolve_local_path(src)
    assert resolved == inner


def test_resolve_local_path_rejects_path_outside_jail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Jail is one subtree; the requested path lives in a sibling.
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    monkeypatch.setattr(settings, "local_source_root", str(allowed))
    monkeypatch.setattr(settings, "allow_unsandboxed_local_sources", False)
    src = SourceConfig(kind="excel", name="x", config={"path": str(sibling)})
    with pytest.raises(LocalPathRejected, match="resolves outside"):
        resolve_local_path(src)


def test_resolve_local_path_rejects_dotdot_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # ``..`` traversal that would escape the jail must be rejected
    # even if the literal string is "inside" the root.
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(settings, "local_source_root", str(allowed))
    monkeypatch.setattr(settings, "allow_unsandboxed_local_sources", False)
    escape = str(allowed / ".." / "secrets")
    src = SourceConfig(kind="excel", name="x", config={"path": escape})
    with pytest.raises(LocalPathRejected, match="resolves outside"):
        resolve_local_path(src)


def test_resolve_local_path_rejects_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A symlink inside the jail pointing OUTSIDE the jail is still an
    # escape -- ``Path.resolve`` follows symlinks.
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    secret = tmp_path / "secret"
    secret.mkdir()
    link = allowed / "shortcut"
    link.symlink_to(secret)

    monkeypatch.setattr(settings, "local_source_root", str(allowed))
    monkeypatch.setattr(settings, "allow_unsandboxed_local_sources", False)
    src = SourceConfig(kind="excel", name="x", config={"path": str(link)})
    with pytest.raises(LocalPathRejected, match="resolves outside"):
        resolve_local_path(src)


def test_resolve_local_path_escape_hatch_bypasses_jail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # ``allow_unsandboxed_local_sources=True`` is the deliberate
    # escape hatch for dev workflows that need a path outside the
    # jail. The missing-path check still applies even with the hatch
    # on -- the worst behavior (walking CWD) is impossible regardless.
    monkeypatch.setattr(settings, "local_source_root", str(tmp_path / "jail"))
    monkeypatch.setattr(settings, "allow_unsandboxed_local_sources", True)
    outside = tmp_path / "outside"
    outside.mkdir()
    src = SourceConfig(kind="excel", name="x", config={"path": str(outside)})
    assert resolve_local_path(src) == outside

    # Missing path is still rejected even with the hatch on.
    with pytest.raises(LocalPathRejected, match="Missing 'path'"):
        resolve_local_path(SourceConfig(kind="excel", name="x", config={}))


def test_resolve_local_path_blank_root_refuses_to_walk(
    monkeypatch: pytest.MonkeyPatch,
):
    # Misconfiguration: an empty ``local_source_root`` with the
    # escape hatch off should fail closed rather than degrade to
    # "walk anywhere" -- the security boundary is the default, and
    # an empty value is a sign of operator error, not opt-out.
    monkeypatch.setattr(settings, "local_source_root", "")
    monkeypatch.setattr(settings, "allow_unsandboxed_local_sources", False)
    src = SourceConfig(kind="excel", name="x", config={"path": "/tmp"})
    with pytest.raises(LocalPathRejected, match="empty"):
        resolve_local_path(src)
