from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from src.config import settings
from src.connectors.base import APIConnector, ConnectorRegistry
from src.models.document import DocumentMetadata, DocumentRef, RawDocument
from src.observability.logging import get_logger

log = get_logger("gitlab_api_connector")

_PER_PAGE = 100
_TIMEOUT = 30.0


class GitLabAPIConnector(APIConnector):
    """Fetches real data from the GitLab REST API, organized by group (team)."""

    platform = "gitlab_api"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        group_ids: list[str] | None = None,
    ) -> None:
        self.base_url = (base_url or settings.gitlab_base_url).rstrip("/")
        self.token = token or settings.gitlab_token
        if not self.token:
            raise ValueError(
                "GitLab API token is required. Set PRISM_GITLAB_TOKEN or pass token= directly."
            )

        if group_ids is not None:
            self.group_ids = group_ids
        else:
            raw = settings.gitlab_group_ids
            self.group_ids = [g.strip() for g in raw.split(",") if g.strip()] if raw else []

        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v4",
            headers={"PRIVATE-TOKEN": self.token},
            timeout=_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_documents(self) -> list[DocumentRef]:
        refs: list[DocumentRef] = []

        if self.group_ids:
            for group_id in self.group_ids:
                group_refs = self._list_group_documents(group_id)
                refs.extend(group_refs)
        else:
            log.warning("no_gitlab_groups_configured")

        log.info("gitlab_api_documents_listed", count=len(refs))
        return refs

    def fetch_document(self, ref: DocumentRef) -> RawDocument:
        fetch_type = ref.file_type

        if fetch_type == ".issue":
            return self._fetch_issue(ref)
        elif fetch_type == ".merge_request":
            return self._fetch_merge_request(ref)
        elif fetch_type == ".wiki":
            return self._fetch_wiki_page(ref)
        elif fetch_type == ".readme":
            return self._fetch_readme(ref)
        else:
            return self._fetch_generic_file(ref)

    # ------------------------------------------------------------------
    # Group / project discovery
    # ------------------------------------------------------------------

    def _list_group_documents(self, group_id: str) -> list[DocumentRef]:
        refs: list[DocumentRef] = []
        group = self._get_group(group_id)
        if not group:
            log.warning("gitlab_group_not_found", group_id=group_id)
            return refs

        group_slug = group.get("full_path", group.get("path", str(group_id)))
        team_name = group.get("name", group_slug)

        projects = self._get_group_projects(group_id)
        log.info("gitlab_group_projects", group=group_slug, project_count=len(projects))

        for project in projects:
            project_refs = self._list_project_documents(project, group_slug)
            refs.extend(project_refs)

        return refs

    def _list_project_documents(self, project: dict, group_slug: str) -> list[DocumentRef]:
        refs: list[DocumentRef] = []
        pid = project["id"]
        project_path = project.get("path_with_namespace", project.get("path", str(pid)))

        # Build a source_path that encodes team info: {group}/{project}/...
        path_prefix = f"{group_slug}/{project.get('path', str(pid))}"

        # README
        refs.append(
            DocumentRef(
                source_platform="gitlab_api",
                source_path=f"{path_prefix}/README.md",
                file_type=".readme",
            )
        )

        # Issues (recent, up to 100)
        for issue in self._paginate(f"/projects/{pid}/issues", params={"state": "all", "order_by": "updated_at", "sort": "desc"}, max_pages=1):
            refs.append(
                DocumentRef(
                    source_platform="gitlab_api",
                    source_path=f"{path_prefix}/issues/issue-{issue['iid']}.json",
                    file_type=".issue",
                )
            )

        # Merge requests (recent, up to 100)
        for mr in self._paginate(f"/projects/{pid}/merge_requests", params={"state": "all", "order_by": "updated_at", "sort": "desc"}, max_pages=1):
            refs.append(
                DocumentRef(
                    source_platform="gitlab_api",
                    source_path=f"{path_prefix}/merge_requests/mr-{mr['iid']}.json",
                    file_type=".merge_request",
                )
            )

        # Wiki pages
        for wiki_page in self._paginate(f"/projects/{pid}/wikis", max_pages=1):
            slug = wiki_page.get("slug", wiki_page.get("title", "page"))
            refs.append(
                DocumentRef(
                    source_platform="gitlab_api",
                    source_path=f"{path_prefix}/wiki/{slug}.md",
                    file_type=".wiki",
                )
            )

        return refs

    # ------------------------------------------------------------------
    # Fetch individual document types
    # ------------------------------------------------------------------

    def _fetch_issue(self, ref: DocumentRef) -> RawDocument:
        project_path, iid = _parse_issue_path(ref.source_path)
        pid = _encode_project_id(project_path)

        data = self._get(f"/projects/{pid}/issues/{iid}")
        if data is None:
            return _empty_doc(ref)

        body = _build_issue_body(data)
        metadata = DocumentMetadata(
            title=data.get("title", ""),
            author=data.get("author", {}).get("name", ""),
            last_modified=_parse_dt(data.get("updated_at")),
            labels=data.get("labels", []),
            source_url=data.get("web_url", ""),
            extra={"state": data.get("state", ""), "iid": data.get("iid")},
        )
        return RawDocument(ref=ref, content=body, metadata=metadata)

    def _fetch_merge_request(self, ref: DocumentRef) -> RawDocument:
        project_path, iid = _parse_mr_path(ref.source_path)
        pid = _encode_project_id(project_path)

        data = self._get(f"/projects/{pid}/merge_requests/{iid}")
        if data is None:
            return _empty_doc(ref)

        body = _build_mr_body(data)
        metadata = DocumentMetadata(
            title=data.get("title", ""),
            author=data.get("author", {}).get("name", ""),
            last_modified=_parse_dt(data.get("updated_at")),
            labels=data.get("labels", []),
            source_url=data.get("web_url", ""),
            extra={
                "state": data.get("state", ""),
                "iid": data.get("iid"),
                "source_branch": data.get("source_branch", ""),
                "target_branch": data.get("target_branch", ""),
            },
        )
        return RawDocument(ref=ref, content=body, metadata=metadata)

    def _fetch_wiki_page(self, ref: DocumentRef) -> RawDocument:
        project_path, slug = _parse_wiki_path(ref.source_path)
        pid = _encode_project_id(project_path)

        data = self._get(f"/projects/{pid}/wikis/{slug}")
        if data is None:
            return _empty_doc(ref)

        content = data.get("content", "")
        title = data.get("title", slug)
        metadata = DocumentMetadata(
            title=title,
            source_url=f"{self.base_url}/{project_path}/-/wikis/{slug}",
        )
        return RawDocument(ref=ref, content=content, metadata=metadata)

    def _fetch_readme(self, ref: DocumentRef) -> RawDocument:
        project_path = _parse_readme_path(ref.source_path)
        pid = _encode_project_id(project_path)

        # Try common README file names
        for fname in ("README.md", "README.rst", "README.txt", "README"):
            data = self._get(f"/projects/{pid}/repository/files/{_encode_file_path(fname)}", params={"ref": "main"})
            if data is None:
                data = self._get(f"/projects/{pid}/repository/files/{_encode_file_path(fname)}", params={"ref": "master"})
            if data is not None:
                break

        if data is None:
            return _empty_doc(ref)

        import base64
        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")

        metadata = DocumentMetadata(
            title=f"README - {project_path.split('/')[-1]}",
            source_url=f"{self.base_url}/{project_path}/-/blob/main/README.md",
        )
        return RawDocument(ref=ref, content=content, metadata=metadata)

    def _fetch_generic_file(self, ref: DocumentRef) -> RawDocument:
        return _empty_doc(ref)

    # ------------------------------------------------------------------
    # GitLab API helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        try:
            resp = self._client.get(path, params=params or {})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            log.warning("gitlab_api_error", path=path, status=e.response.status_code)
            return None
        except httpx.HTTPError as e:
            log.warning("gitlab_api_request_failed", path=path, error=str(e))
            return None

    def _get_group(self, group_id: str) -> dict | None:
        encoded = _encode_path(group_id)
        return self._get(f"/groups/{encoded}")

    def _get_group_projects(self, group_id: str) -> list[dict]:
        encoded = _encode_path(group_id)
        return list(
            self._paginate(
                f"/groups/{encoded}/projects",
                params={"include_subgroups": "true", "archived": "false", "order_by": "last_activity_at", "sort": "desc"},
            )
        )

    def _paginate(self, path: str, params: dict | None = None, max_pages: int = 5) -> list[dict]:
        results: list[dict] = []
        params = dict(params or {})
        params.setdefault("per_page", str(_PER_PAGE))
        page = 1

        while page <= max_pages:
            params["page"] = str(page)
            try:
                resp = self._client.get(path, params=params)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                results.extend(data)
                if len(data) < _PER_PAGE:
                    break
                page += 1
            except httpx.HTTPError as e:
                log.warning("gitlab_api_paginate_error", path=path, page=page, error=str(e))
                break

        return results

    def close(self) -> None:
        self._client.close()


# ------------------------------------------------------------------
# Path parsing helpers
# ------------------------------------------------------------------

def _parse_issue_path(source_path: str) -> tuple[str, int]:
    """Extract project path and issue IID from source_path like 'group/project/issues/issue-42.json'."""
    parts = source_path.split("/")
    issues_idx = parts.index("issues")
    project_path = "/".join(parts[:issues_idx])
    filename = parts[-1]  # issue-42.json
    iid = int(filename.replace("issue-", "").replace(".json", ""))
    return project_path, iid


def _parse_mr_path(source_path: str) -> tuple[str, int]:
    """Extract project path and MR IID from source_path like 'group/project/merge_requests/mr-10.json'."""
    parts = source_path.split("/")
    mr_idx = parts.index("merge_requests")
    project_path = "/".join(parts[:mr_idx])
    filename = parts[-1]  # mr-10.json
    iid = int(filename.replace("mr-", "").replace(".json", ""))
    return project_path, iid


def _parse_wiki_path(source_path: str) -> tuple[str, str]:
    """Extract project path and wiki slug from source_path like 'group/project/wiki/my-page.md'."""
    parts = source_path.split("/")
    wiki_idx = parts.index("wiki")
    project_path = "/".join(parts[:wiki_idx])
    slug = parts[-1].replace(".md", "")
    return project_path, slug


def _parse_readme_path(source_path: str) -> str:
    """Extract project path from source_path like 'group/project/README.md'."""
    parts = source_path.split("/")
    return "/".join(parts[:-1])  # everything except README.md


def _encode_path(path_or_id: str) -> str:
    """URL-encode a GitLab group/project path for use in API URLs."""
    try:
        int(path_or_id)
        return path_or_id  # numeric ID, no encoding needed
    except ValueError:
        import urllib.parse
        return urllib.parse.quote(path_or_id, safe="")


def _encode_project_id(project_path: str) -> str:
    """Encode a project path like 'my-group/my-project' for the GitLab API."""
    return _encode_path(project_path)


def _encode_file_path(file_path: str) -> str:
    """Encode a file path for the repository files API."""
    import urllib.parse
    return urllib.parse.quote(file_path, safe="")


# ------------------------------------------------------------------
# Content builders
# ------------------------------------------------------------------

def _build_issue_body(data: dict) -> str:
    parts = []
    title = data.get("title", "")
    if title:
        parts.append(f"# {title}")

    state = data.get("state", "")
    if state:
        parts.append(f"State: {state}")

    labels = data.get("labels", [])
    if labels:
        parts.append(f"Labels: {', '.join(labels)}")

    assignees = data.get("assignees", [])
    if assignees:
        names = [a.get("name", a.get("username", "")) for a in assignees]
        parts.append(f"Assignees: {', '.join(names)}")

    milestone = data.get("milestone")
    if milestone:
        parts.append(f"Milestone: {milestone.get('title', '')}")

    description = data.get("description", "")
    if description:
        parts.append(f"\n{description}")

    return "\n\n".join(parts)


def _build_mr_body(data: dict) -> str:
    parts = []
    title = data.get("title", "")
    if title:
        parts.append(f"# {title}")

    state = data.get("state", "")
    if state:
        parts.append(f"State: {state}")

    source = data.get("source_branch", "")
    target = data.get("target_branch", "")
    if source and target:
        parts.append(f"Branch: {source} → {target}")

    labels = data.get("labels", [])
    if labels:
        parts.append(f"Labels: {', '.join(labels)}")

    author = data.get("author", {})
    if author:
        parts.append(f"Author: {author.get('name', author.get('username', ''))}")

    reviewers = data.get("reviewers", [])
    if reviewers:
        names = [r.get("name", r.get("username", "")) for r in reviewers]
        parts.append(f"Reviewers: {', '.join(names)}")

    description = data.get("description", "")
    if description:
        parts.append(f"\n{description}")

    return "\n\n".join(parts)


def _empty_doc(ref: DocumentRef) -> RawDocument:
    return RawDocument(ref=ref, content="", metadata=DocumentMetadata())


def _parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


ConnectorRegistry.register_api("gitlab_api", GitLabAPIConnector)
