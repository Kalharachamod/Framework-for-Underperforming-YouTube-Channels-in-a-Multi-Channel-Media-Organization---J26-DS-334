"""Researcher-only annotation export CLI.

Exports are deliberately outside the public Streamlit interface. Local mode
uses the development admin token; Supabase mode requires a server-side database
connection and an active researcher-admin row.
"""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from .assignments import create_development_annotators, generate_assignments, load_annotation_comments
from .auth import development_tokens, hash_invitation_token
from .config import load_config
from .exports import export_for_researcher
from .local_store import LocalAnnotationStore
from .supabase_store import SupabaseAnnotationStore


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description="Export Component 2 annotation responses for the researcher")
    parser.add_argument("--mode", choices=("local", "supabase"), default=config.mode)
    parser.add_argument("--output", type=Path, help="Output CSV path outside Git-tracked data")
    parser.add_argument("--admin-id", help="Active Supabase researcher_admin ID")
    parser.add_argument("--revoke-participant-id", help="Revoke one active Supabase participant session")
    args = parser.parse_args(argv)
    if not args.output and not args.revoke_participant_id:
        parser.error("--output is required for export")

    if args.mode == "local":
        if args.revoke_participant_id:
            parser.error("Participant revocation requires --mode supabase")
        frame = _local_export(config)
    else:
        if not config.supabase_db_url:
            parser.error("SUPABASE_DB_URL is required for --mode supabase")
        if not args.admin_id:
            parser.error("--admin-id is required for --mode supabase")
        store = SupabaseAnnotationStore(
            config.supabase_db_url,
            run_id=config.annotation_run_id,
            connect_timeout=config.db_connect_timeout,
        )
        if args.revoke_participant_id:
            store.revoke_participant(args.revoke_participant_id, args.admin_id)
            print(f"Revoked participant session {args.revoke_participant_id}")
            return 0
        if not args.output:
            parser.error("--output is required for export")
        frame = store.export_for_admin(args.admin_id)

    if not args.output:
        parser.error("--output is required for export")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    print(f"Exported {len(frame)} rows to {args.output}")
    return 0


def _local_export(config):
    comments = load_annotation_comments(config.annotation_csv_path)
    assignments = generate_assignments(comments, seed=config.assignment_seed)
    store = LocalAnnotationStore(config.local_db_path)
    try:
        store.initialize(comments, assignments, create_development_annotators(config.portal_secret))
        token = os.getenv("COMPONENT2_ADMIN_TOKEN", "").strip()
        if not token:
            token = getpass.getpass("Researcher admin token: ")
        requester = store.authenticate(hash_invitation_token(token, config.portal_secret))
        if requester is None or not requester.is_admin:
            raise PermissionError("Researcher admin token is not authorized")
        return export_for_researcher(store, requester)
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
