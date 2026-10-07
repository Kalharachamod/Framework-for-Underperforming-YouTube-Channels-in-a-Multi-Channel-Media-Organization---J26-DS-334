"""Organization channel discovery.

Given an organization name (e.g. "Derana"), find the YouTube channels that
probably belong to it: its main channel and sub-channels, including ones whose
names do not contain the organization name.

YouTube does not publish channel ownership, so this produces *candidates with
evidence and a confidence level*. A person reviews them and confirms which
belong (``confirm_organization``); only confirmed channels are saved.

Evidence used (YouTube Data API only):
  * name match: the organization name in the channel title or handle
  * linked: listed in the featured/multi-channel section of a matching channel
  * links back: the candidate itself lists a matching channel
  * shared website: same website domain in the description as a matching channel
  * mention: organization name in the description
  * same country as the matching channels
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from shared.data_collection.youtube_client import YouTubeClient
from shared.utils import paths

Confidence = Literal["high", "medium", "low"]

HIGH, MEDIUM = 5.0, 3.0
MAX_SEEDS = 5  # matching channels whose linked channels are followed
MAX_LINK_BACK_CHECKS = 20  # linked candidates checked for links back (1 unit each)

# Website domains that say nothing about ownership.
GENERIC_DOMAINS = {
    "youtube.com", "youtu.be", "facebook.com", "fb.com", "fb.me", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "linkedin.com", "t.me", "wa.me", "whatsapp.com", "bit.ly", "linktr.ee", "google.com",
    "goo.gl", "play.google.com", "apps.apple.com", "apple.com", "spotify.com", "gmail.com", "threads.net",
}
_URL = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/[^\s]*)?", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[a-z]{2,})", re.IGNORECASE)


@dataclass
class Candidate:
    channel_id: str
    title: str
    handle: str | None
    country: str | None
    subscriber_count: int | None
    video_count: int | None
    score: float = 0.0
    confidence: Confidence = "low"
    evidence: list[str] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    organization: str
    discovered_at: str
    quota_used: int
    candidates: list[Candidate]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- discovery -----------------------------------------------------------------

def discover_organization(
    organization: str,
    client: YouTubeClient,
    *,
    max_search_results: int = 25,
    region_code: str | None = None,
) -> DiscoveryResult:
    """Search for an organization's channels and rank them by evidence."""
    org = organization.strip()
    if len(org) < 2:
        raise ValueError("organization name must have at least 2 characters")
    start_quota = client.quota_used

    found = client.search_channels(org, max_results=max_search_results, region_code=region_code)
    channels = {c["id"]: c for c in client.get_channels(found)}

    # Seeds: the strongest name matches; their linked channels reveal sub-channels.
    seeds = sorted(
        (cid for cid, c in channels.items() if _name_match(org, c) >= 1.0),
        key=lambda cid: (-_name_match(org, channels[cid]), -_subs(channels[cid]), cid),
    )[:MAX_SEEDS]

    linked_from: dict[str, list[str]] = {}
    links_out: dict[str, list[str]] = {}
    for seed in seeds:
        links = client.get_linked_channels(seed)
        links_out[seed] = links
        for cid in links:
            linked_from.setdefault(cid, []).append(seed)

    # Does each linked candidate link back to a matching channel? (not expanded further)
    for cid in [c for c in linked_from if c not in links_out][:MAX_LINK_BACK_CHECKS]:
        links_out[cid] = client.get_linked_channels(cid)

    new_ids = [cid for cid in linked_from if cid not in channels]
    for c in client.get_channels(new_ids):
        channels[c["id"]] = c

    seed_countries = {_country(channels[s]) for s in seeds} - {None}
    candidates = [
        _score(org, channels[cid], channels, seeds, linked_from, links_out, seed_countries)
        for cid in channels
    ]
    candidates.sort(key=lambda c: (-c.score, -(c.subscriber_count or 0), c.channel_id))
    return DiscoveryResult(
        organization=org,
        discovered_at=_now(),
        quota_used=client.quota_used - start_quota,
        candidates=candidates,
    )


def _score(org, ch, channels, seeds, linked_from, links_out, seed_countries) -> Candidate:
    cid = ch["id"]
    snippet, stats = ch.get("snippet", {}), ch.get("statistics", {})
    cand = Candidate(
        channel_id=cid,
        title=snippet.get("title", ""),
        handle=snippet.get("customUrl"),
        country=_country(ch),
        subscriber_count=None if stats.get("hiddenSubscriberCount") else _int(stats.get("subscriberCount")),
        video_count=_int(stats.get("videoCount")),
    )
    score, ev = 0.0, cand.evidence

    name = _name_match(org, ch)
    if name >= 3.0:
        score += 3.0
        ev.append("organization name in channel title")
    elif name >= 1.0:
        score += 1.5
        ev.append("organization name partly in title or handle")

    sources = [s for s in linked_from.get(cid, []) if s != cid]
    if sources:
        score += 3.0
        ev.append("linked by " + ", ".join(sorted(channels[s]["snippet"]["title"] for s in sources)))
    if any(s in links_out.get(cid, []) for s in seeds if s != cid):
        score += 1.0
        ev.append("links back to a matching channel")

    # Compare with the *other* matching channels only, never with itself.
    other_domains = set().union(*(_domains(channels[s]) for s in seeds if s != cid))
    shared = sorted(_domains(ch) & other_domains)
    if shared:
        score += 2.0
        ev.append("same website as matching channels: " + ", ".join(shared))

    if _normalize(org) in _normalize(snippet.get("description", "")) and name < 3.0:
        score += 1.0
        ev.append("organization named in description")
    if cand.country and cand.country in seed_countries and score > 0:
        score += 0.5
        ev.append(f"same country ({cand.country})")

    cand.score = round(score, 2)
    cand.confidence = "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"
    if not ev:
        ev.append("returned by search only")
    return cand


# --- confirmation and storage ------------------------------------------------------

def organizations_dir() -> Path:
    return paths.PROJECT_ROOT / "config" / "organizations"


def review_dir() -> Path:
    return paths.get_data_paths().raw / "discovery"


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not slug:
        raise ValueError(f"cannot build a file name from organization {name!r}")
    return slug


def save_review(result: DiscoveryResult) -> Path:
    """Save candidates for review (git-ignored data/raw/discovery/), so confirming costs no quota."""
    path = review_dir() / f"{slugify(result.organization)}.json"
    _write_json(path, result.to_dict())
    return path


def load_review(organization: str) -> DiscoveryResult:
    path = review_dir() / f"{slugify(organization)}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No discovery results for {organization!r}; run discovery first ({path})")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["candidates"] = [Candidate(**c) for c in data["candidates"]]
    return DiscoveryResult(**data)


def confirm_organization(result: DiscoveryResult, channel_ids: list[str], *, overwrite: bool = False) -> Path:
    """Save the reviewer-confirmed channels as the organization's channel list (config/)."""
    by_id = {c.channel_id: c for c in result.candidates}
    unknown = [cid for cid in channel_ids if cid not in by_id]
    if unknown:
        raise ValueError(f"not among the discovered candidates: {unknown}")
    if not channel_ids:
        raise ValueError("confirm at least one channel")

    path = organizations_dir() / f"{slugify(result.organization)}.json"
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass overwrite=True to replace it")
    chosen = [by_id[cid] for cid in dict.fromkeys(channel_ids)]
    _write_json(path, {
        "organization": result.organization,
        "confirmed_at": _now(),
        "discovered_at": result.discovered_at,
        "method": "youtube_data_api: channel search + linked channels + description evidence; reviewer-confirmed",
        "channels": [
            {"channel_id": c.channel_id, "title": c.title, "handle": c.handle,
             "confidence": c.confidence, "evidence": c.evidence}
            for c in chosen
        ],
    })
    return path


def load_organization(organization: str) -> dict[str, Any]:
    path = organizations_dir() / f"{slugify(organization)}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Organization {organization!r} has no confirmed channel list ({path})")
    return json.loads(path.read_text(encoding="utf-8"))


def organization_channel_ids(organization: str) -> list[str]:
    return [c["channel_id"] for c in load_organization(organization)["channels"]]


# --- helpers ---------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[\W_]+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in _normalize(text).split() if t]


def _name_match(org: str, ch: dict[str, Any]) -> float:
    """3 = all org words in the title; 1 = some words in title or handle; 0 = none."""
    org_tokens = _tokens(org)
    snippet = ch.get("snippet", {})
    title = set(_tokens(snippet.get("title", "")))
    if org_tokens and all(t in title for t in org_tokens):
        return 3.0
    handle = _normalize(snippet.get("customUrl", "")).replace(" ", "")
    joined = "".join(org_tokens)
    if any(t in title for t in org_tokens) or (joined and joined in handle) or (
        joined and joined in "".join(_tokens(snippet.get("title", "")))
    ):
        return 1.0
    return 0.0


def _domains(ch: dict[str, Any]) -> set[str]:
    text = ch.get("snippet", {}).get("description", "") or ""
    found = {m.group(1).lower() for m in _URL.finditer(text)} | {m.group(1).lower() for m in _EMAIL.finditer(text)}
    roots = set()
    for d in found:
        parts = d.split(".")
        root = ".".join(parts[-3:]) if len(parts) >= 3 and len(parts[-1]) == 2 and len(parts[-2]) <= 3 else ".".join(parts[-2:])
        if root not in GENERIC_DOMAINS and not any(root.endswith("." + g) for g in GENERIC_DOMAINS):
            roots.add(root)
    return roots


def _country(ch: dict[str, Any]) -> str | None:
    return ch.get("snippet", {}).get("country") or ch.get("brandingSettings", {}).get("channel", {}).get("country")


def _subs(ch: dict[str, Any]) -> int:
    return _int(ch.get("statistics", {}).get("subscriberCount")) or 0


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
