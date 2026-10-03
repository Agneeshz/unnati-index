"""Database fixtures.

Integration tests run against `TEST_DATABASE_URL` when it is set (CI uses a Postgres service
container). Locally they start an in-memory PGlite server (WASM Postgres from the repo's npm
tooling), so no Postgres install or Docker is needed. Run `npm install` at the repo root first."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pg8000.native
import pytest

from unnati.db import connect

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "db" / "migrations"
PGLITE_SERVER = REPO / "node_modules" / "@electric-sql" / "pglite-socket" / "dist" / "scripts" / "server.js"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            connect(url).close()
            return
        except (OSError, pg8000.native.InterfaceError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@pytest.fixture(scope="session")
def database_url():
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    node = shutil.which("node")
    if not node or not PGLITE_SERVER.exists():
        pytest.skip("no TEST_DATABASE_URL and no PGlite server (run `npm install` at the repo root)")
    port = _free_port()
    proc = subprocess.Popen(
        [node, str(PGLITE_SERVER), "--db=memory://", f"--port={port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres?sslmode=disable"
    try:
        _wait_for(url)
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _migration_up_sql() -> list[str]:
    sql = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        sql.append(text.split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0])
    return sql


@pytest.fixture()
def db(database_url):
    """A connection to a freshly migrated, empty schema."""
    conn = connect(database_url)
    try:
        conn.run("drop schema if exists public cascade")
        conn.run("create schema public")
        for up in _migration_up_sql():
            conn.run(up)
        yield conn
    finally:
        conn.close()
