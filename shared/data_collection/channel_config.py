"""Which channels the research collects (config/research_channels.json).

Groups (e.g. ``owned``, ``competitor``; more can be added) list confirmed
organizations from ``config/organizations/<slug>.json`` and/or individual
channel ids. A channel may appear in only one group.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.data_collection.org_discovery import load_organization
from shared.utils import paths

CONFIG_FILE = "research_channels.json"
_CHANNEL_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


class ChannelConfigError(ValueError):
    """The channel configuration is missing, malformed or empty."""


@dataclass(frozen=True)
class ConfiguredChannel:
    channel_id: str
    group: str        # e.g. "owned", "competitor"
    source: str       # "organization:<slug>" or "channel_ids"


def config_path() -> Path:
    return paths.PROJECT_ROOT / "config" / CONFIG_FILE


def load_channels(groups: list[str] | None = None, *, path: Path | None = None) -> list[ConfiguredChannel]:
    """Resolve the configured channels (optionally only some groups), in config order."""
    path = path or config_path()
    if not path.is_file():
        raise ChannelConfigError(f"channel configuration not found: {path}")
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChannelConfigError(f"{path.name} is not valid JSON: {exc}") from None
    all_groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(all_groups, dict) or not all_groups:
        raise ChannelConfigError(f"{path.name} must contain a non-empty 'groups' object")

    selected = groups or list(all_groups)
    unknown = [g for g in selected if g not in all_groups]
    if unknown:
        raise ChannelConfigError(f"unknown group(s) {unknown}; configured: {sorted(all_groups)}")

    channels: list[ConfiguredChannel] = []
    owner: dict[str, str] = {}
    for group, spec in all_groups.items():  # resolve all groups, so cross-group duplicates are caught
        if not isinstance(spec, dict):
            raise ChannelConfigError(f"group '{group}' must be an object")
        for slug in spec.get("organizations", []) or []:
            try:
                ids = [c["channel_id"] for c in load_organization(slug)["channels"]]
            except FileNotFoundError:
                raise ChannelConfigError(
                    f"group '{group}': organization '{slug}' has no confirmed list "
                    f"(run: python -m shared.data_collection.discover search \"{slug}\")"
                ) from None
            channels += _add(group, ids, f"organization:{slug}", owner)
        channels += _add(group, spec.get("channel_ids", []) or [], "channel_ids", owner)

    result = [c for c in channels if c.group in selected]
    if not result:
        raise ChannelConfigError(f"no channels configured for group(s) {selected} in {path.name}")
    return result


def _add(group: str, ids: list[Any], source: str, owner: dict[str, str]) -> list[ConfiguredChannel]:
    added = []
    for cid in ids:
        if not isinstance(cid, str) or not _CHANNEL_ID.fullmatch(cid.strip()):
            raise ChannelConfigError(f"group '{group}': invalid channel id {cid!r}")
        cid = cid.strip()
        if cid in owner:
            if owner[cid] != group:
                raise ChannelConfigError(f"channel {cid} is in both '{owner[cid]}' and '{group}'")
            continue  # same group listed twice (e.g. organization + explicit id)
        owner[cid] = group
        added.append(ConfiguredChannel(cid, group, source))
    return added
