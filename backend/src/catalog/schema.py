"""Schema for the declarative Org -> Team -> Service catalog.

This module owns the tables that describe *what* the organization looks like.
The ingestion pipeline, in turn, writes scope-tagged documents (in
``kg_documents``) and chunks (in OpenSearch) that reference these tables.

The first time the catalog initializes it also drops the *legacy* ownership
tables that have been replaced by this declared model -- ``kg_teams``,
``kg_services``, ``kg_ownership``, ``kg_service_tech``, ``kg_document_services``.
Because service identity moves from ``TEXT`` to ``UUID``, ``kg_dependencies``
and ``kg_documents`` are also wiped and re-created so their foreign keys line up
with the new model. The plan explicitly calls this out: seed-era rows are not
preserved across the migration.
"""

from __future__ import annotations

CATALOG_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teams (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);
CREATE INDEX IF NOT EXISTS teams_org_idx ON teams(org_id);

CREATE TABLE IF NOT EXISTS services (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    repo_url    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, name)
);
CREATE INDEX IF NOT EXISTS services_team_idx ON services(team_id);

CREATE TABLE IF NOT EXISTS sources (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID REFERENCES organizations(id) ON DELETE CASCADE,
    team_id           UUID REFERENCES teams(id) ON DELETE CASCADE,
    service_id        UUID REFERENCES services(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL,
    name              TEXT NOT NULL,
    config            JSONB NOT NULL DEFAULT '{}'::jsonb,
    secret_ref        TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    last_ingested_at  TIMESTAMPTZ,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (org_id     IS NOT NULL)::int
      + (team_id    IS NOT NULL)::int
      + (service_id IS NOT NULL)::int = 1
    )
);
CREATE INDEX IF NOT EXISTS sources_org_idx     ON sources(org_id);
CREATE INDEX IF NOT EXISTS sources_team_idx    ON sources(team_id);
CREATE INDEX IF NOT EXISTS sources_service_idx ON sources(service_id);
CREATE INDEX IF NOT EXISTS sources_kind_idx    ON sources(kind);

-- Phase 1 stores plaintext secrets (PATs etc.). The plan marks this as a
-- deliberate TODO to replace in Phase 3 with a real secret store. The separate
-- table keeps tokens out of the source list query and makes it easy to revoke.
CREATE TABLE IF NOT EXISTS source_secrets (
    source_id  UUID PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
    token      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


# kg_documents + kg_dependencies are re-created against the new scope model.
# They used TEXT keys keyed to regex-inferred team/service names; now they
# carry UUID foreign keys into ``teams``/``services``. See plan "Schema
# Deltas -> Modified tables".
DOCUMENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kg_documents (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    path          TEXT,
    platform      TEXT,
    last_modified TIMESTAMPTZ,
    author        TEXT,
    source_url    TEXT DEFAULT '',
    source_id     UUID REFERENCES sources(id) ON DELETE CASCADE,
    org_id        UUID REFERENCES organizations(id) ON DELETE CASCADE,
    team_id       UUID REFERENCES teams(id) ON DELETE CASCADE,
    service_id    UUID REFERENCES services(id) ON DELETE CASCADE
);
-- Self-healing for pre-existing databases that were created before the
-- source_url column was added.
ALTER TABLE kg_documents ADD COLUMN IF NOT EXISTS source_url TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS kg_documents_path_idx       ON kg_documents(path);
CREATE INDEX IF NOT EXISTS kg_documents_platform_idx   ON kg_documents(platform);
CREATE INDEX IF NOT EXISTS kg_documents_source_idx     ON kg_documents(source_id);
CREATE INDEX IF NOT EXISTS kg_documents_org_idx        ON kg_documents(org_id);
CREATE INDEX IF NOT EXISTS kg_documents_team_idx       ON kg_documents(team_id);
CREATE INDEX IF NOT EXISTS kg_documents_service_idx    ON kg_documents(service_id);

-- Service dependencies. Edges have two flavours:
--   * Internal -- ``to_service_id`` references another row in ``services``.
--   * External -- ``to_external_name`` is a free-text label for something
--     outside the declared catalog (Stripe, Auth0, an upstream team's API
--     not yet declared, etc.). ``to_service_id`` is NULL in that case.
-- A row is exactly one kind, enforced by the CHECK constraint.
CREATE TABLE IF NOT EXISTS kg_dependencies (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_service_id          UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    to_service_id            UUID REFERENCES services(id) ON DELETE CASCADE,
    to_external_name         TEXT,
    to_external_description  TEXT NOT NULL DEFAULT '',
    source                   TEXT NOT NULL DEFAULT '',
    last_updated             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (to_service_id IS NOT NULL AND to_external_name IS NULL)
        OR
        (to_service_id IS NULL AND to_external_name IS NOT NULL)
    ),
    UNIQUE (from_service_id, to_service_id)
);
CREATE INDEX IF NOT EXISTS kg_dependencies_to_idx ON kg_dependencies(to_service_id);
-- Case-insensitive uniqueness for external targets: the UI dedupes
-- by ``lower(name)`` so ``Stripe`` and ``stripe`` should collide at the
-- DB layer too. A function-based partial unique index lets us preserve
-- the user's display casing while preventing dupes that differ only in
-- case. ``ON CONFLICT (from_service_id, lower(to_external_name)) DO
-- UPDATE`` in the repo references this index by its expression columns.
CREATE UNIQUE INDEX IF NOT EXISTS kg_dependencies_external_name_lower_uniq
    ON kg_dependencies (from_service_id, lower(to_external_name))
    WHERE to_external_name IS NOT NULL;
"""


# Registry uniqueness is composite on ``(source_id, source_path)`` so two
# sources can each have their own ``README.md`` without colliding. The
# update-vs-skip decision is content-hash driven inside the ingest loop:
# same hash => skip, different hash => delete old chunks + re-index.
REGISTRY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_registry (
    document_id       TEXT PRIMARY KEY,
    source_platform   TEXT NOT NULL,
    source_path       TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    last_ingested_at  TIMESTAMPTZ DEFAULT NOW(),
    chunk_count       INTEGER DEFAULT 0,
    status            TEXT DEFAULT 'pending',
    source_id         UUID REFERENCES sources(id) ON DELETE CASCADE,
    UNIQUE (source_id, source_path)
);
CREATE INDEX IF NOT EXISTS idx_registry_source_path  ON document_registry(source_path);
CREATE INDEX IF NOT EXISTS idx_registry_status       ON document_registry(status);
CREATE INDEX IF NOT EXISTS idx_registry_source_id    ON document_registry(source_id);
"""


# A one-shot DDL block that drops the legacy ownership / pinning tables. The
# detection query below decides whether to run it: if ``kg_teams`` or
# ``kg_ownership`` still exist, we are on the old schema and need to migrate.
# On a fresh DB neither exists, so the DROPs are no-ops.
LEGACY_DROP_SQL = """
DROP TABLE IF EXISTS kg_ownership         CASCADE;
DROP TABLE IF EXISTS kg_document_services CASCADE;
DROP TABLE IF EXISTS kg_service_tech      CASCADE;
DROP TABLE IF EXISTS kg_technologies      CASCADE;
DROP TABLE IF EXISTS kg_services          CASCADE;
DROP TABLE IF EXISTS kg_teams             CASCADE;
"""


# When migrating an existing deployment the pre-existing ``kg_documents`` and
# ``kg_dependencies`` have a different shape (TEXT service keys, no scope
# columns). They also cite kg_services / kg_teams which we just dropped. The
# simplest path -- consistent with the plan's "truncate existing seed-derived
# rows" -- is to drop and recreate them.
LEGACY_DOCUMENTS_RESET_SQL = """
DROP TABLE IF EXISTS kg_dependencies CASCADE;
DROP TABLE IF EXISTS kg_documents    CASCADE;
DROP TABLE IF EXISTS document_registry CASCADE;
"""


LEGACY_DETECTION_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('kg_teams', 'kg_ownership', 'kg_service_tech', 'kg_document_services')
) AS has_legacy_tables,
EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'kg_documents'
      AND column_name = 'source_id'
) AS kg_documents_has_scope,
EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'kg_dependencies'
      AND column_name = 'from_service_id'
) AS kg_dependencies_has_uuid;
"""
