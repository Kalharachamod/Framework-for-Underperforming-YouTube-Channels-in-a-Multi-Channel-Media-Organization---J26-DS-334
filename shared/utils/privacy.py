"""Privacy processing: pseudonymization of commenter identifiers.

A commenter's YouTube channel id is replaced by a keyed hash before anything is
stored:

    "UCabc..."  ->  "anon_" + HMAC-SHA256(COMMENTER_HASH_SALT, "UCabc...")  (64 hex chars)

* Same commenter -> same pseudonym, so cross-channel audience links still work.
* The original id cannot be recovered without the secret salt, and the salt
  stops anyone from re-computing pseudonyms for known channel ids.
* The schema (shared.schemas) stays a plain data definition; ``store_records``
  calls this module, so raw commenter ids never reach Parquet.

All team members must use the same salt, and it must never change; otherwise
pseudonyms from different machines or dates stop matching.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

from shared.utils import paths  # noqa: F401  (loads .env)

HASH_PREFIX = "anon_"
MIN_SALT_LENGTH = 32
_HASHED = re.compile(rf"^{HASH_PREFIX}[0-9a-f]{{64}}$")
_PLACEHOLDERS = {"", "your_commenter_hash_salt_here", "changeme"}


class PrivacyConfigError(RuntimeError):
    """The hashing salt is missing or too weak; commenter ids cannot be stored safely."""


def get_salt() -> bytes:
    """The team's secret salt from ``COMMENTER_HASH_SALT`` (never logged or returned in errors)."""
    salt = os.getenv("COMMENTER_HASH_SALT", "").strip()
    if salt.lower() in _PLACEHOLDERS:
        raise PrivacyConfigError(
            "COMMENTER_HASH_SALT is not set in .env; comments with commenter ids cannot be stored. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    if len(salt) < MIN_SALT_LENGTH:
        raise PrivacyConfigError(f"COMMENTER_HASH_SALT must be at least {MIN_SALT_LENGTH} characters")
    return salt.encode("utf-8")


def is_pseudonymized(value: str | None) -> bool:
    return isinstance(value, str) and bool(_HASHED.fullmatch(value))


def pseudonymize_id(raw_id: str, salt: bytes | None = None) -> str:
    """Keyed hash of a commenter id. Already-pseudonymized values are returned unchanged."""
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ValueError("commenter id must be a non-empty string")
    if is_pseudonymized(raw_id):
        return raw_id
    key = salt if salt is not None else get_salt()
    digest = hmac.new(key, raw_id.strip().encode("utf-8"), hashlib.sha256).hexdigest()
    return HASH_PREFIX + digest
