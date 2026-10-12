"""Component 3 dashboard aggregates (read-only, from the stored research snapshot and artifacts).

Everything here is an aggregate of public YouTube Data API v3 fields collected into the snapshot
(view, like and comment counts are the public counts observed when each video was collected) or of
stored research artifacts. No commenter identifier leaves the aggregation queries, nothing is
estimated, and values that were not observed stay NULL.
"""

from __future__ import annotations

from typing import Any

from backend.database.component_3_artifacts import TOPICS_DIR, Component3Store
from backend.services.component_3.service import (ArtifactUnavailable, Component3Service, InvalidParameter, _clean,
                                                  _public, _v)

COUNTS_NOTE = ("View, like and comment counts are the public counts observed when each collected video was "
               "collected; totals cover the collected videos only (collection limits apply), not whole channels.")
GRANULARITIES = {"week": "week", "month": "month"}
SORTS = {"views": "view_count", "likes": "like_count", "comments": "comment_count"}   # code-defined columns only


class DashboardService:
    def __init__(self, base: Component3Service):
        self.base = base
        self.store: Component3Store = base.store

    def _files(self, sid: str, *names: str) -> dict:
        return {n: self.store.snapshot_dataset(sid, n) for n in names}

    # --- summary ------------------------------------------------------------------------------------

    def summary(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        sid = snap.snapshot_id
        df = self.store.aggregate("""
            SELECT (SELECT count(*) FROM channels) AS channels,
                   (SELECT sum(subscriber_count) FROM channels) AS subscribers,
                   (SELECT count(*) FROM channels WHERE subscriber_count IS NULL) AS channels_hidden_subscribers,
                   (SELECT count(*) FROM videos) AS videos,
                   (SELECT sum(view_count) FROM videos) AS views,
                   (SELECT sum(like_count) FROM videos) AS likes,
                   (SELECT count(*) FROM videos WHERE view_count IS NULL) AS videos_without_views,
                   (SELECT sum(comment_count) FROM videos) AS public_comments,
                   (SELECT count(*) FROM comments) AS collected_comments,
                   (SELECT count(DISTINCT author_channel_id) FROM comments) AS unique_commenters,
                   (SELECT min(published_at) FROM videos) AS first_video,
                   (SELECT max(published_at) FROM videos) AS last_video
        """, self._files(sid, "channels", "videos", "comments"))
        r = {k: _v(v) for k, v in df.iloc[0].items()}
        return _clean({"snapshot_id": sid, "extracted_at": snap.extracted_at or snap.created_at, **r,
                       "note": COUNTS_NOTE})

    # --- channel performance ------------------------------------------------------------------------

    def channels(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        df = self.store.aggregate("""
            WITH v AS (SELECT channel_id, count(*) AS videos, sum(view_count) AS views, sum(like_count) AS likes,
                              sum(comment_count) AS public_comments, max(published_at) AS last_video
                       FROM videos GROUP BY channel_id),
                 c AS (SELECT channel_id, count(*) AS collected_comments,
                              count(DISTINCT author_channel_id) AS unique_commenters
                       FROM comments GROUP BY channel_id)
            SELECT ch.channel_id, ch.channel_name, ch.subscriber_count, ch.view_count AS channel_views,
                   ch.video_count AS channel_videos, v.videos, v.views, v.likes, v.public_comments, v.last_video,
                   c.collected_comments, c.unique_commenters
            FROM channels ch LEFT JOIN v USING (channel_id) LEFT JOIN c USING (channel_id)
            ORDER BY v.views DESC NULLS LAST, ch.channel_id
        """, self._files(snap.snapshot_id, "channels", "videos", "comments"))
        items = [{k: _v(v) for k, v in rec.items()} for rec in df.to_dict("records")]
        for it in items:
            it["videos"] = it["videos"] or 0
            it["collected_comments"] = it["collected_comments"] or 0
            it["unique_commenters"] = it["unique_commenters"] or 0
        return _clean({"snapshot_id": snap.snapshot_id, "items": items, "note": COUNTS_NOTE})

    # --- top videos ---------------------------------------------------------------------------------

    def top_videos(self, snapshot_id: str | None, limit: int, channel_id: str | None,
                   sort: str = "views") -> dict[str, Any]:
        if sort not in SORTS:
            raise InvalidParameter(f"sort must be one of {sorted(SORTS)}")
        col = SORTS[sort]
        snap = self.base._snapshot(snapshot_id)
        where, params = f"WHERE v.{col} IS NOT NULL", []
        if channel_id:
            node = self.base.channel_node(channel_id)
            self.base._require_channel(snap, node)
            where += " AND v.channel_id = ?"
            params.append(_public(node))
        df = self.store.aggregate(f"""
            SELECT v.video_id, v.title, v.channel_id, ch.channel_name, v.published_at, v.view_count AS views,
                   v.like_count AS likes, v.comment_count AS comments, v.duration_seconds
            FROM videos v LEFT JOIN channels ch USING (channel_id) {where}
            ORDER BY v.{col} DESC, v.video_id LIMIT {int(limit)}
        """, self._files(snap.snapshot_id, "videos", "channels"), params)
        items = [{**{k: _v(v) for k, v in rec.items()},
                  "thumbnail_url": f"https://i.ytimg.com/vi/{rec['video_id']}/mqdefault.jpg",
                  "video_url": f"https://www.youtube.com/watch?v={rec['video_id']}"} for rec in df.to_dict("records")]
        return _clean({"snapshot_id": snap.snapshot_id, "sort": sort, "items": items, "note": COUNTS_NOTE})

    # --- views over time --------------------------------------------------------------------------------

    def views_timeline(self, snapshot_id: str | None, granularity: str, periods: int) -> dict[str, Any]:
        if granularity not in GRANULARITIES:
            raise InvalidParameter(f"granularity must be one of {sorted(GRANULARITIES)}")
        snap = self.base._snapshot(snapshot_id)
        unit = GRANULARITIES[granularity]
        df = self.store.aggregate(f"""
            WITH b AS (SELECT date_trunc('{unit}', published_at AT TIME ZONE 'UTC') AS period, channel_id,
                              count(*) AS videos, sum(view_count) AS views, sum(comment_count) AS comments
                       FROM videos GROUP BY 1, 2),
                 recent AS (SELECT DISTINCT period FROM b ORDER BY period DESC LIMIT {int(periods)})
            SELECT b.* FROM b JOIN recent USING (period) ORDER BY period, channel_id
        """, self._files(snap.snapshot_id, "videos"))
        periods_list = sorted({str(p)[:10] for p in df["period"]})
        names = dict(zip(*self._names(snap.snapshot_id)))
        series = []
        for cid, g in df.groupby("channel_id", sort=True):
            by = {str(p)[:10]: r for p, r in zip(g["period"], g.itertuples())}
            series.append({"channel_id": cid, "channel_name": names.get(cid),
                           "views": [_v(by[p].views) if p in by else 0 for p in periods_list],
                           "videos": [int(by[p].videos) if p in by else 0 for p in periods_list],
                           "total_views": int(sum(_v(r.views) or 0 for r in g.itertuples()))})
        series.sort(key=lambda x: -x["total_views"])
        return _clean({"snapshot_id": snap.snapshot_id, "granularity": granularity, "periods": periods_list,
                       "series": series,
                       "note": "Views of the collected videos grouped by their publish date (counts observed at "
                               "collection). This is not a channel's daily view history: zero means no collected "
                               "video was published in that period."})

    def _names(self, sid: str) -> tuple[list[str], list[str]]:
        ch = self.store.query(self.store.snapshot_dataset(sid, "channels"), ["channel_id", "channel_name"])
        return ch["channel_id"].astype(str).tolist(), ch["channel_name"].tolist()

    # --- overlap network ----------------------------------------------------------------------------

    def overlap(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        path = self.store.features_dir(snap) / "channel_pair_features.parquet"
        if not path.is_file():
            raise ArtifactUnavailable(f"graph features (STEP 14) are not available for snapshot {snap.snapshot_id}")
        pf = self.store.query(path, ["channel_a", "channel_b", "shared_commenter_count", "jaccard_similarity"])
        nodes = self.channels(snap.snapshot_id)["items"]
        multi = self.store.aggregate("""
            SELECT count(*) AS n FROM (SELECT author_channel_id FROM comments WHERE author_channel_id IS NOT NULL
                                       GROUP BY 1 HAVING count(DISTINCT channel_id) >= 2)
        """, self._files(snap.snapshot_id, "comments"))
        return _clean({
            "snapshot_id": snap.snapshot_id,
            "commenters_on_multiple_channels": int(multi["n"].iloc[0]),
            "nodes": [{"channel_id": n["channel_id"], "channel_name": n["channel_name"],
                       "unique_commenters": n["unique_commenters"]} for n in nodes],
            "edges": sorted(({"source_channel_id": _public(r.channel_a), "destination_channel_id": _public(r.channel_b),
                              "shared_commenters": int(r.shared_commenter_count),
                              "jaccard_similarity": _v(r.jaccard_similarity)} for r in pf.itertuples()),
                            key=lambda e: -e["shared_commenters"]),
            "note": "Undirected pairs of channels with at least one commenter observed on both (aggregate counts). "
                    "Shared commenters are not audience migration."})

    # --- topics ----------------------------------------------------------------------------------------

    def topics(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        runs = [m for m in self.store.runs(snap.snapshot_id, TOPICS_DIR, "top", "topic_run.json")
                if (m["_dir"] / "topics.parquet").is_file()]
        if not runs:
            raise ArtifactUnavailable(f"no topic run with topic clusters for snapshot {snap.snapshot_id}")
        run = runs[-1]
        df = self.store.aggregate("""
            SELECT t.topic_id, count(*) AS videos, sum(v.view_count) AS views,
                   arg_max(v.channel_id, cnt.n) AS top_channel_id
            FROM video_topics t JOIN videos v USING (video_id)
            JOIN (SELECT t2.topic_id, v2.channel_id, count(*) AS n FROM video_topics t2 JOIN videos v2 USING (video_id)
                  GROUP BY 1, 2) cnt ON cnt.topic_id = t.topic_id AND cnt.channel_id = v.channel_id
            GROUP BY t.topic_id ORDER BY videos DESC, t.topic_id
        """, {"video_topics": run["_dir"] / "video_topics.parquet", **self._files(snap.snapshot_id, "videos")})
        total = int(df["videos"].sum()) if len(df) else 0
        names = dict(zip(*self._names(snap.snapshot_id)))
        items = [{"topic_id": r.topic_id, "label": f"Topic {int(str(r.topic_id).lstrip('t')) + 1}",
                  "videos": int(r.videos), "share": (int(r.videos) / total) if total else None,
                  "views": _v(r.views), "top_channel_name": names.get(r.top_channel_id)} for r in df.itertuples()]
        return _clean({"snapshot_id": snap.snapshot_id, "topic_run_id": run["_dir"].name, "items": items,
                       "note": "Topic clusters are unlabelled KMeans clusters of video text embeddings (STEP 18); "
                               "the numbers are cluster sizes, not trends."})

    # --- top audience bridges ----------------------------------------------------------------------------

    def top_bridges(self, snapshot_id: str | None, experiment_id: str | None, limit: int) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        run = self.base._experiment(snap, experiment_id)
        path = run["_dir"] / "audience_bridge_scores.parquet"
        df = self.store.query(path, ["source_channel_id", "destination_channel_id", "audience_bridge_score",
                                     "confidence", "shared_commenters", "rank"],
                              where="audience_bridge_score IS NOT NULL AND audience_bridge_score > 0 "
                                    "AND source_channel_id <> destination_channel_id",
                              order_by="audience_bridge_score DESC, source_channel_id, destination_channel_id",
                              limit=limit)
        names = dict(zip(*self._names(snap.snapshot_id)))
        items = [{"source_channel_id": _public(r.source_channel_id),
                  "source_channel_name": names.get(_public(r.source_channel_id)),
                  "destination_channel_id": _public(r.destination_channel_id),
                  "destination_channel_name": names.get(_public(r.destination_channel_id)),
                  "audience_bridge_score": _v(r.audience_bridge_score), "confidence": _v(r.confidence),
                  "shared_commenters": _v(r.shared_commenters), "rank": _v(r.rank)} for r in df.itertuples()]
        return _clean({"snapshot_id": snap.snapshot_id, "experiment_id": run["experiment_id"], "items": items,
                       "note": "Highest stored Audience Bridge Scores across all sources (potential audience bridge "
                               "signals; provisional formula)."})

