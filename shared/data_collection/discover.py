"""Command line for organization channel discovery.

    python -m shared.data_collection.discover search "Derana"        # find candidates (uses quota)
    python -m shared.data_collection.discover review "Derana"        # show saved candidates again (no quota)
    python -m shared.data_collection.discover confirm "Derana" 1 2 5 # save chosen channels to config/organizations/
    python -m shared.data_collection.discover confirm "Derana" high  # all high-confidence candidates
    python -m shared.data_collection.discover show "Derana"          # show the confirmed channel list
"""

from __future__ import annotations

import argparse
import sys

from shared.data_collection.org_discovery import (
    DiscoveryResult,
    confirm_organization,
    discover_organization,
    load_organization,
    load_review,
    save_review,
)
from shared.data_collection.youtube_client import DAILY_QUOTA, YouTubeAPIError, YouTubeClient


def print_candidates(result: DiscoveryResult) -> None:
    print(f"\nCandidates for '{result.organization}' (discovered {result.discovered_at}, "
          f"quota used {result.quota_used}/{DAILY_QUOTA}):\n")
    print(f"{'#':>3}  {'confidence':<10} {'score':>5}  {'subscribers':>11}  channel")
    print("-" * 78)
    for i, c in enumerate(result.candidates, 1):
        subs = f"{c.subscriber_count:,}" if c.subscriber_count is not None else "hidden"
        handle = f" ({c.handle})" if c.handle else ""
        print(f"{i:>3}  {c.confidence:<10} {c.score:>5}  {subs:>11}  {c.title}{handle}  [{c.channel_id}]")
        print(f"{'':>36}- " + "; ".join(c.evidence))
    print("\nYouTube does not publish ownership: confirm only channels you know belong to the organization.")


def select(result: DiscoveryResult, choices: list[str]) -> list[str]:
    """Turn '1 2 5' or 'high' / 'medium' (and above) into channel ids."""
    if len(choices) == 1 and choices[0] in ("high", "medium"):
        levels = {"high": {"high"}, "medium": {"high", "medium"}}[choices[0]]
        return [c.channel_id for c in result.candidates if c.confidence in levels]
    ids = []
    for token in ",".join(choices).replace(" ", "").split(","):
        if not token:
            continue
        if not token.isdigit() or not 1 <= int(token) <= len(result.candidates):
            raise ValueError(f"'{token}' is not a candidate number from 1 to {len(result.candidates)}")
        ids.append(result.candidates[int(token) - 1].channel_id)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="discover", description="Find an organization's YouTube channels.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search", help="search YouTube (uses ~100-150 quota units)")
    p.add_argument("organization")
    p.add_argument("--max-results", type=int, default=25)
    p.add_argument("--region", help="2-letter region code to bias search, e.g. LK")
    sub.add_parser("review", help="show saved candidates (no quota)").add_argument("organization")
    p = sub.add_parser("confirm", help="save chosen candidates as the organization's channel list")
    p.add_argument("organization")
    p.add_argument("choices", nargs="+", help="candidate numbers (1 2 5), or 'high' / 'medium'")
    p.add_argument("--overwrite", action="store_true", help="replace an existing confirmed list")
    sub.add_parser("show", help="show the confirmed channel list").add_argument("organization")
    args = parser.parse_args(argv)

    try:
        if args.command == "search":
            client = YouTubeClient()
            result = discover_organization(args.organization, client,
                                           max_search_results=args.max_results, region_code=args.region)
            path = save_review(result)
            print_candidates(result)
            print(f"\nSaved for review: {path}")
            print(f'Next: python -m shared.data_collection.discover confirm "{args.organization}" <numbers>')
        elif args.command == "review":
            print_candidates(load_review(args.organization))
        elif args.command == "confirm":
            result = load_review(args.organization)
            path = confirm_organization(result, select(result, args.choices), overwrite=args.overwrite)
            print(f"Saved confirmed channel list: {path}")
        elif args.command == "show":
            org = load_organization(args.organization)
            print(f"{org['organization']} - confirmed {org['confirmed_at']}")
            for c in org["channels"]:
                print(f"  {c['title']} ({c.get('handle') or '-'})  [{c['channel_id']}]  {c['confidence']}")
    except (YouTubeAPIError, ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
