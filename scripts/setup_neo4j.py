#!/usr/bin/env python3
import asyncio
import sys
import time

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "backend")
)

from neo4j import GraphDatabase
from src.config import settings

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Team) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (tech:Technology) REQUIRE tech.name IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.path)",
    "CREATE INDEX IF NOT EXISTS FOR (s:Service) ON (s.repo_url)",
    "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.platform)",
]


def wait_for_neo4j(max_retries: int = 30) -> GraphDatabase.driver:
    for attempt in range(max_retries):
        try:
            driver = GraphDatabase.driver(
                settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
            )
            driver.verify_connectivity()
            print("Neo4j connected")
            return driver
        except Exception:
            print(f"Waiting for Neo4j... ({attempt + 1}/{max_retries})")
            time.sleep(2)
    raise RuntimeError("Neo4j not available")


def setup():
    driver = wait_for_neo4j()

    with driver.session() as session:
        for stmt in CONSTRAINTS:
            try:
                session.run(stmt)
                print(f"  Created: {stmt[:60]}...")
            except Exception as e:
                print(f"  Skipped: {str(e)[:80]}")

        for stmt in INDEXES:
            try:
                session.run(stmt)
                print(f"  Created: {stmt[:60]}...")
            except Exception as e:
                print(f"  Skipped: {str(e)[:80]}")

    driver.close()
    print("Neo4j setup complete")


if __name__ == "__main__":
    setup()
