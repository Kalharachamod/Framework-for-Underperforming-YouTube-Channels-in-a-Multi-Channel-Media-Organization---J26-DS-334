"""API configuration from environment variables (loaded from .env by shared.utils.paths).

  API_CORS_ORIGINS               comma-separated frontend origins (default http://localhost:5173);
                                 "*" is refused: CORS must name the allowed frontends
  API_MAX_PAGE_SIZE              upper bound for ?limit= (default 100)
  API_REQUEST_TIMEOUT_SECONDS    per-request time limit, answered with 504 (default 30)
  DATA_DIR                       research data root (shared with the research pipeline)

No secret is read or needed here: the API reads local research artifacts only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import shared.utils.paths  # noqa: F401  (loads .env)

DEFAULT_ORIGINS = ("http://localhost:5173",)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = DEFAULT_ORIGINS
    max_page_size: int = 100
    request_timeout_seconds: float = 30.0
    api_version: str = "1.0.0"
    title: str = "Growth Intelligence API"

    def __post_init__(self):
        if any(o.strip() == "*" for o in self.cors_origins):
            raise ConfigError("API_CORS_ORIGINS must list explicit origins; '*' is not allowed")
        if any(not o.startswith(("http://", "https://")) for o in self.cors_origins):
            raise ConfigError("every CORS origin must start with http:// or https://")
        if not 1 <= self.max_page_size <= 1000:
            raise ConfigError("API_MAX_PAGE_SIZE must be between 1 and 1000")
        if not 0 < self.request_timeout_seconds <= 600:
            raise ConfigError("API_REQUEST_TIMEOUT_SECONDS must be in (0, 600]")


def load_settings() -> Settings:
    origins = os.getenv("API_CORS_ORIGINS")
    try:
        return Settings(
            cors_origins=tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip()) if origins
            else DEFAULT_ORIGINS,
            max_page_size=int(os.getenv("API_MAX_PAGE_SIZE", "100")),
            request_timeout_seconds=float(os.getenv("API_REQUEST_TIMEOUT_SECONDS", "30")),
        )
    except ValueError as exc:
        raise ConfigError(f"invalid API configuration: {exc}") from None
