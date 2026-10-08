"""Supabase / PostgreSQL configuration and connections.

Configuration (``.env`` only, never in code or git):

    SUPABASE_URL       project URL, e.g. https://<ref>.supabase.co     (future REST / dashboard use)
    SUPABASE_ANON_KEY  public anon key                                (future dashboard; cannot read research data)
    SUPABASE_DB_URL    server-side PostgreSQL connection string       (collectors, migrations, research code)

``SUPABASE_DB_URL`` contains the database password; it is the privileged,
server-side credential and is never logged or shown in errors.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import psycopg

from shared.utils import paths  # noqa: F401  (loads .env)

CONNECT_TIMEOUT_SECONDS = 10
_PLACEHOLDER = re.compile(r"your[_-]|<|>|\.\.\.", re.IGNORECASE)
_PASSWORD_IN_URL = re.compile(r"(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+(@)")


class DatabaseConfigError(RuntimeError):
    """Database configuration is missing or still a placeholder."""


class DatabaseConnectionError(RuntimeError):
    """Could not connect to the database (message never contains the password)."""


@dataclass(frozen=True)
class SupabaseConfig:
    url: str | None
    anon_key: str | None
    db_url: str | None

    def __repr__(self) -> str:  # never show secrets
        return (f"SupabaseConfig(url={self.url!r}, anon_key={'***' if self.anon_key else None}, "
                f"db_url={redact_url(self.db_url) if self.db_url else None!r})")

    @property
    def db_host(self) -> str | None:
        return urlsplit(self.db_url).hostname if self.db_url else None


def load_config() -> SupabaseConfig:
    """Read the Supabase settings; unset or placeholder values become None."""
    def value(name: str) -> str | None:
        v = os.getenv(name, "").strip()
        return None if not v or _PLACEHOLDER.search(v) else v

    return SupabaseConfig(value("SUPABASE_URL"), value("SUPABASE_ANON_KEY"), value("SUPABASE_DB_URL"))


def require_db_url(config: SupabaseConfig | None = None) -> str:
    cfg = config or load_config()
    if not cfg.db_url:
        raise DatabaseConfigError(
            "SUPABASE_DB_URL is not set in .env. Use the Supabase 'Session pooler' connection string "
            "(Project → Connect). See docs/architecture/supabase.md"
        )
    if not cfg.db_url.startswith(("postgresql://", "postgres://")):
        raise DatabaseConfigError("SUPABASE_DB_URL must start with postgresql://")
    return cfg.db_url


def redact_url(url: str) -> str:
    return _PASSWORD_IN_URL.sub(r"\1***\2", url)


def connect(db_url: str | None = None, *, autocommit: bool = False) -> psycopg.Connection:
    """Open a PostgreSQL connection (UTC session, short connect timeout).

    Supabase hosts get ``sslmode=require`` unless the URL sets it. Prepared
    statements are disabled so the Supabase connection pooler is supported.
    """
    url = db_url or require_db_url()
    kwargs: dict = {"connect_timeout": CONNECT_TIMEOUT_SECONDS, "application_name": "j26-ds-334",
                    "autocommit": autocommit, "prepare_threshold": None}
    host = urlsplit(url).hostname or ""
    if host.endswith((".supabase.co", ".supabase.com")) and "sslmode=" not in url:
        kwargs["sslmode"] = "require"
    try:
        conn = psycopg.connect(url, **kwargs)
    except psycopg.Error as exc:
        raise DatabaseConnectionError(
            f"Cannot connect to the database at {host or 'unknown host'}: {_clean(exc, url)}"
        ) from None
    conn.execute("SET TIME ZONE 'UTC'")
    if not autocommit:
        conn.commit()
    return conn


@contextmanager
def database(db_url: str | None = None) -> Iterator[psycopg.Connection]:
    """Connection that commits on success, rolls back on error, and always closes."""
    conn = connect(db_url)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clean(exc: Exception, url: str) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    password = urlsplit(url).password
    text = redact_url(text)
    return text.replace(password, "***") if password else text
