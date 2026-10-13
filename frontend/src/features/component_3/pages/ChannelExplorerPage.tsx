import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LineChart } from "../../../components/charts/LineChart";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader, Pager, Select, StatCard, StatGrid, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";

const PAGE = 10;

export function ChannelExplorerPage() {
  const { channels, snapshotId } = useResearch();
  const [params, setParams] = useSearchParams();
  const channel = params.get("channel") ?? "";
  const [offset, setOffset] = useState(0);
  const { experimentId } = useResearch();
  const detail = useApi((s) => component3Api.channel(channel, { snapshotId }, s), [channel, snapshotId], channel !== "");
  const allPairs = useApi((s) => component3Api.bridgePairs({ snapshotId, experimentId }, s), [snapshotId, experimentId], channel !== "");
  const topicSim = useApi((s) => component3Api.topicSimilarity({ snapshotId }, s), [snapshotId], channel !== "");
  const graph = useApi((s) => component3Api.graphSummary({ snapshotId }, s), [snapshotId], channel !== "");
  const timeline = useApi((s) => component3Api.viewsTimeline({ snapshotId }, "month", 12, s), [snapshotId], channel !== "");
  const outgoing = allPairs.status === "success"
    ? allPairs.data.items.filter((r) => r.source_channel_id === channel && r.audience_bridge_score !== null).sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9))
    : [];
  const meanScore = outgoing.length ? outgoing.reduce((a, r) => a + (r.audience_bridge_score ?? 0), 0) / outgoing.length : null;
  const connectivity = graph.status === "success" ? graph.data.channel_connectivity.find((c) => c.channel_id === channel) ?? null : null;
  const related = topicSim.status === "success"
    ? topicSim.data.cells.filter((c) => c.source_channel_id === channel && c.topic_similarity !== null)
      .sort((a, b) => (b.topic_similarity ?? 0) - (a.topic_similarity ?? 0)).slice(0, 5)
      .map((c) => ({ id: c.destination_channel_id, v: c.topic_similarity, name: topicSim.data.channels.find((x) => x.channel_id === c.destination_channel_id)?.channel_name ?? c.destination_channel_id }))
    : [];
  const series = timeline.status === "success" ? timeline.data.series.find((x) => x.channel_id === channel) ?? null : null;
  const pairs = useApi((s) => component3Api.channelPairs(channel, { snapshotId }, PAGE, offset, s), [channel, snapshotId, offset], channel !== "");
  const options = channels.status === "success" ? channels.data.items.map((c) => ({ value: c.channel_id, label: c.channel_name ?? c.channel_id })) : [];

  return (
    <>
      <PageHeader title="Channel Explorer" description="Channel metadata, aggregate graph features and shared-commenter overlap. Only aggregate counts are shown." />
      <Card>
        <Select
          id="explorer-channel"
          label="Channel"
          value={channel}
          placeholder="Select a channel…"
          options={options}
          disabled={channels.status !== "success"}
          onChange={(v) => {
            setOffset(0);
            setParams(v ? { channel: v } : {});
          }}
        />
        {channels.status === "error" && <ErrorState error={channels.error} />}
      </Card>
      {channel === "" && <EmptyState title="Select a channel to inspect it." />}
      {detail.status === "loading" && <Loading />}
      {detail.status === "error" && <ErrorState error={detail.error} onRetry={detail.reload} />}
      {detail.status === "success" && (
        <StatGrid label="Channel summary">
          <StatCard label="Stored videos" value={int(detail.data.stored_video_count)} hint={`coverage ${pct(detail.data.collection_coverage, 1)} of public videos`} />
          <StatCard label="Comments" value={int(detail.data.comment_count)} hint="collected, public" />
          <StatCard label="Unique commenters" value={int(detail.data.unique_commenter_count)} hint="aggregate count" />
          <StatCard label="Subscribers" value={int(detail.data.observed_subscriber_count)} hint="public, at collection" />
        </StatGrid>
      )}
      {detail.status === "success" && (
        <div className="grid grid--2">
          <Card title={detail.data.channel_name ?? detail.data.channel_id}>
            <KeyValues
              rows={[
                ["Channel id", <code key="c">{detail.data.channel_id}</code>],
                ["Created", date(detail.data.published_at)],
                ["Subscribers (public, at collection)", int(detail.data.observed_subscriber_count)],
                ["Views (public)", int(detail.data.observed_view_count)],
                ["Videos on YouTube", int(detail.data.observed_api_video_count)],
              ]}
            />
          </Card>
          <Card
            title="Aggregate research features"
            actions={<Badge tone={detail.data.features_status === "available" ? "ok" : "neutral"}>Features {detail.data.features_status}</Badge>}
          >
            {detail.data.features_status === "missing" ? (
              <p className="muted">STEP 14 features have not been computed for this snapshot.</p>
            ) : (
              <KeyValues
                rows={[
                  ["Stored videos", int(detail.data.stored_video_count)],
                  ["Collection coverage (stored / public videos)", pct(detail.data.collection_coverage, 1)],
                  ["Comments", int(detail.data.comment_count)],
                  ["Replies", int(detail.data.reply_count)],
                  ["Unique commenters", int(detail.data.unique_commenter_count)],
                  ["Commenters with 2+ comments", int(detail.data.active_commenter_count)],
                  ["Avg comments per video", num(detail.data.avg_comments_per_video, 2)],
                  ["Active days", int(detail.data.active_days)],
                  ["First / last comment", `${date(detail.data.first_interaction_at)} / ${date(detail.data.last_interaction_at)}`],
                ]}
              />
            )}
          </Card>
        </div>
      )}
      {detail.status === "success" && (
        <>
          <section className="rs-strip" aria-label="Research profile">
            <div className="rs-strip__cell"><span>Graph connectivity</span><strong>{connectivity ? int(connectivity.connected_channels) : "—"}</strong><small>channels sharing commenters</small></div>
            <div className="rs-strip__cell"><span>Shared commenters (summed)</span><strong>{connectivity ? int(connectivity.shared_commenters_summed) : "—"}</strong><small>over channel pairs</small></div>
            <div className="rs-strip__cell"><span>Mean outgoing bridge score</span><strong>{num(meanScore, 3)}</strong><small>of {int(outgoing.length)} stored scores</small></div>
            <div className="rs-strip__cell"><span>Strongest destination</span><strong className="rs-strip__name">{outgoing[0]?.destination_channel_name ?? "—"}</strong><small>{outgoing[0] ? `score ${num(outgoing[0].audience_bridge_score, 3)}` : ""}</small></div>
          </section>
          <div className="grid grid--2">
            <Card title="Top potential destinations" info="Highest stored Audience Bridge Scores with this channel as the source (potential bridges, not audience movement).">
              {allPairs.status === "loading" && <Loading />}
              {allPairs.status === "error" && <ErrorState error={allPairs.error} />}
              {allPairs.status === "success" && (outgoing.length === 0 ? <EmptyState title="No scored destination for this channel." /> : (
                <ol className="rel-list">
                  {outgoing.slice(0, 5).map((r) => (
                    <li key={r.destination_channel_id}>
                      <Link className="rel-list__name" to={`/bridges?source=${encodeURIComponent(channel)}&destination=${encodeURIComponent(r.destination_channel_id)}`}>{r.destination_channel_name}</Link>
                      <span className="rel-list__track"><span style={{ width: `${(r.audience_bridge_score ?? 0) * 100}%` }} /></span>
                      <span className="rel-list__value">{num(r.audience_bridge_score, 3)}</span>
                    </li>
                  ))}
                </ol>
              ))}
            </Card>
            <Card title="Topic profile" info="Channels whose content profile is most similar to this channel's (cosine similarity of video-text embeddings).">
              {topicSim.status === "loading" && <Loading />}
              {topicSim.status === "error" && <ErrorState error={topicSim.error} />}
              {topicSim.status === "success" && (related.length === 0 ? <EmptyState title="No topic profile for this channel." /> : (
                <ol className="rel-list">
                  {related.map((r) => (
                    <li key={r.id}>
                      <span className="rel-list__name">{r.name}</span>
                      <span className="rel-list__track"><span style={{ width: `${Math.max(0, r.v ?? 0) * 100}%` }} /></span>
                      <span className="rel-list__value">{num(r.v, 3)}</span>
                    </li>
                  ))}
                </ol>
              ))}
            </Card>
          </div>
          <Card title="Temporal activity" info={timeline.status === "success" ? timeline.data.note : "Collected videos by publish month."}>
            {timeline.status === "loading" && <Loading />}
            {timeline.status === "error" && <ErrorState error={timeline.error} />}
            {timeline.status === "success" && (!series ? <EmptyState title="No collected video in the last 12 publish months." /> : (
              <LineChart height={200} yLabel="Videos" labels={timeline.data.periods.map((p) => p.slice(0, 7))}
                summary={`Collected videos of ${detail.data.channel_name} by publish month`}
                series={[{ key: "videos", label: "Collected videos per month", color: "var(--viz-primary)", values: series.videos }]} />
            ))}
          </Card>
        </>
      )}
      {channel !== "" && (
        <Card title="Channels sharing commenters">
          {pairs.status === "loading" && <Loading />}
          {pairs.status === "error" && <ErrorState error={pairs.error} onRetry={pairs.reload} />}
          {pairs.status === "success" && pairs.data.items.length === 0 && (
            <EmptyState title="No shared commenters">
              <p>No commenter of this channel was observed on another research channel.</p>
            </EmptyState>
          )}
          {pairs.status === "success" && pairs.data.items.length > 0 && (
            <>
              <TableWrap label="Related channels">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Channel</th>
                      <th scope="col">Shared commenters</th>
                      <th scope="col" title="Shared / union of the two commenter sets">Jaccard</th>
                      <th scope="col" title="Share of this channel's commenters also seen on the other channel">Overlap from this channel</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairs.data.items.map((p) => (
                      <tr key={p.destination_channel_id}>
                        <td>{p.destination_channel_name ?? p.destination_channel_id}</td>
                        <td className="num">{int(p.shared_commenters)}</td>
                        <td className="num">{num(p.jaccard_similarity, 4)}</td>
                        <td className="num">{pct(p.directional_overlap_source_to_destination, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
              <Pager total={pairs.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
              <p className="muted">{pairs.data.note}</p>
            </>
          )}
        </Card>
      )}
      {detail.status === "success" && <Provenance snapshotId={detail.data.snapshot_id} extra={detail.data.as_of ? `features as of ${date(detail.data.as_of)}` : undefined} />}
    </>
  );
}
