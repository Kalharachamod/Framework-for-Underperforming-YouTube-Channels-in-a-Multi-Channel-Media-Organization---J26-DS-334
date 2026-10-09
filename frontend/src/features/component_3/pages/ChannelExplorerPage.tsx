import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader, Pager, Select, TableWrap } from "../../../components/common/ui";
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
  const detail = useApi((s) => component3Api.channel(channel, { snapshotId }, s), [channel, snapshotId], channel !== "");
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
