"""Lightweight identity helpers for the annotation portal."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedAnnotator:
    annotator_id: str
    display_name: str
    role: str
    active: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role == "researcher_admin"


@dataclass(frozen=True)
class ParticipantSession:
    participant_id: str
    display_name: str
    section_id: str
    section_label: str
    assignment_template_id: str
    active: bool = True
    return_code: str | None = None


def generate_invitation_token() -> str:
    """Create a high-entropy invitation token.

    This function is for researcher-approved provisioning only. The repository
    never stores real generated tokens.
    """
    return secrets.token_urlsafe(32)


def hash_invitation_token(token: str, secret: str) -> str:
    normalized = token.strip()
    if not normalized:
        raise ValueError("Invitation token is required")
    return hashlib.sha256(f"{secret}:{normalized}".encode("utf-8")).hexdigest()


def generate_return_code() -> str:
    """Create a private return code for resuming one participant session."""
    return f"c2-{secrets.token_urlsafe(12)}"


def hash_private_code(code: str, secret: str) -> str:
    normalized = code.strip()
    if not normalized:
        raise ValueError("Private return code is required")
    return hashlib.sha256(f"{secret}:{normalized}".encode("utf-8")).hexdigest()


class ResumeAttemptLimiter:
    """Small process-local guard against repeated return-code guesses.

    The return code has high entropy and is stored only as a hash. This limiter
    adds friction to repeated failures in one app process; deployment-level
    request throttling remains necessary for a public service.
    """

    def __init__(self, limit: int = 20, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str = "resume") -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts[key]
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return False
            attempts.append(now)
            return True


def token_matches(token: str, expected_hash: str, secret: str) -> bool:
    return hmac.compare_digest(hash_invitation_token(token, secret), expected_hash)


def development_tokens() -> dict[str, str]:
    """Local-only tokens used by the development SQLite store."""
    tokens = {"primary_annotator": "dev-primary-token"}
    tokens.update({f"volunteer_{index}": f"dev-volunteer-{index}-token" for index in range(1, 6)})
    tokens["researcher_admin"] = "dev-admin-token"
    return tokens
