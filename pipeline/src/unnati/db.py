"""Database access via pg8000, a pure-Python Postgres driver.

Pure Python on purpose: it needs no native libpq, so it runs anywhere Python runs, including
machines whose application-control policy blocks unsigned native extensions."""

from __future__ import annotations

import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pg8000.native

from unnati.config import Settings, require

Connection = pg8000.native.Connection

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def connect(database_url: str | None = None) -> Connection:
    """Open a connection from a ``postgresql://user:pass@host:port/db?sslmode=...`` URL.

    TLS is used unless ``sslmode=disable`` or the host is local, which suits Neon (TLS required)
    and the local PGlite test server (no TLS)."""
    url = urlparse(require(database_url or Settings.from_env().database_url, "DATABASE_URL"))
    if url.scheme not in ("postgres", "postgresql"):
        raise ValueError(f"unsupported database URL scheme {url.scheme!r}")
    sslmode = parse_qs(url.query).get("sslmode", [""])[0]
    use_tls = sslmode != "disable" and url.hostname not in _LOCAL_HOSTS
    return Connection(
        user=unquote(url.username or "postgres"),
        password=unquote(url.password) if url.password else None,
        host=url.hostname or "localhost",
        port=url.port or 5432,
        database=unquote(url.path.lstrip("/")) or "postgres",
        ssl_context=ssl.create_default_context() if use_tls else None,
    )


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    conn.run("begin")
    try:
        yield conn
    except BaseException:
        conn.run("rollback")
        raise
    conn.run("commit")


def scalar(conn: Connection, sql: str, **params: Any) -> Any:
    rows = conn.run(sql, **params)
    return rows[0][0] if rows else None
