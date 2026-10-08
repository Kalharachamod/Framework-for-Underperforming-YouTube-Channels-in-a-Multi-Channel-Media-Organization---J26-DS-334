"""One collection run: channels -> videos -> comments -> research snapshot (optional).

    python -m shared.data_collection.run_collection                         # all groups, defaults
    python -m shared.data_collection.run_collection --max-videos 50 --snapshot
    python -m shared.data_collection.run_collection --group competitor --max-videos 20

Meant to be run repeatedly (e.g. daily by Windows Task Scheduler / cron) so the
research gets observations over time. Each stage reuses its collector; a stage
that fails stops the run only when later stages depend on it (no channels ->
no videos). A short run log is written to data/raw/collection_runs/.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from shared.utils import paths


def main(argv: list[str] | None = None) -> int:
    import argparse

    from research.component_3.preprocessing import research_dataset
    from shared.data_collection import channel_collector, comment_collector, video_collector

    ap = argparse.ArgumentParser(prog="run_collection", description="Run the full YouTube collection pipeline.")
    ap.add_argument("--group", action="append", help="configured channel group (repeatable; default: all)")
    ap.add_argument("--max-videos", type=int, default=50, help="newest videos per channel (default 50)")
    ap.add_argument("--max-threads", type=int, default=100, help="comment threads per video (default 100)")
    ap.add_argument("--all-comments", action="store_true",
                    help="re-collect comments of all stored videos (default: new videos + incremental)")
    ap.add_argument("--snapshot", action="store_true", help="afterwards create and prepare a research snapshot")
    args = ap.parse_args(argv)

    groups = sum((["--group", g] for g in (args.group or [])), [])
    stages = [
        ("channels", channel_collector.main, groups),
        ("videos", video_collector.main, groups + ["--max-videos", str(args.max_videos)]),
        ("comments", comment_collector.main,
         groups + ["--max-threads", str(args.max_threads)] + ([] if args.all_comments else ["--incremental"])),
    ]
    if args.snapshot:
        stages.append(("research_snapshot", research_dataset.main, ["--extract"]))

    started = datetime.now(timezone.utc)
    log = {"started_at": started.isoformat(timespec="seconds"), "arguments": vars(args), "stages": []}
    code = 0
    for name, fn, stage_args in stages:
        print(f"\n=== {name} ===", flush=True)
        t0 = time.perf_counter()
        rc = fn(stage_args)
        log["stages"].append({"stage": name, "exit_code": rc, "seconds": round(time.perf_counter() - t0, 1)})
        if rc != 0:
            code = 1
            if rc == 2:  # configuration / connection problem: the stage could not run at all
                print(f"Stopping: stage '{name}' could not run (exit {rc}).", file=sys.stderr)
                break
    log["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log["exit_code"] = code
    out = paths.get_data_paths().raw / "collection_runs" / f"{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    print(f"\nRun log: {out}  (exit {code}; 1 = some items failed, see stage output)")
    return code


if __name__ == "__main__":
    sys.exit(main())
