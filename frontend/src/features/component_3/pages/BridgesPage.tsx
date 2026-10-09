import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { HorizontalBarChart } from "../../../components/charts/BarChart";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Card, Notice, PageHeader, Pager, Select, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { num } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";

const PAGE = 10;

export function BridgesPage() {
  const { channels, snapshotId, experimentId } = useResearch();
  const [params, setParams] = useSearchParams();
  const source = params.get("source") ?? "";
  const [offset, setOffset] = useState(0);
  const [includeUnscored, setIncludeUnscored] = useState(false);
  const ranking = useApi(
    (s) => component3Api.ranking(source, { snapshotId, experimentId }, PAGE, offset, includeUnscored, s),
    [source, snapshotId, experimentId, offset, includeUnscored],
    source !== "",
  );
  const options = channels.status === "success" ? channels.data.items.map((c) => ({ value: c.channel_id, label: c.channel_name ?? c.channel_id })) : [];
  // Defensive: a source is never its own destination (the API already excludes self pairs).
  const rows = ranking.status === "success" ? ranking.data.items.filter((r) => r.destination_channel_id !== ranking.data.source_channel_id) : [];

  return (
    <>
      <PageHeader title="Audience Bridges" description="Destination channels ranked as potential audience bridges for a selected source channel." />
      <Notice>{LIMITATIONS}</Notice>
      <Card>
        <div className="controls">
          <Select
            id="bridge-source"
            label="Source channel"
            value={source}
            placeholder="Select a channel…"
            options={options}
            disabled={channels.status !== "success"}
            onChange={(v) => {
              setOffset(0);
              setParams(v ? { source: v } : {});
            }}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={includeUnscored}
              onChange={(e) => {
                setOffset(0);
                setIncludeUnscored(e.target.checked);
              }}
            />
            Include pairs without a score
          </label>
        </div>
        {channels.status === "error" && <ErrorState error={channels.error} />}
      </Card>

      {source === "" && <EmptyState title="Select a source channel to see its ranked destinations." />}
      {ranking.status === "loading" && <Loading label="Loading rankings…" />}
      {ranking.status === "error" && <ErrorState error={ranking.error} onRetry={ranking.reload} />}
      {ranking.status === "success" && rows.length === 0 && (
        <EmptyState title="No ranked destinations">
          <p>This source has no scored destination in the selected experiment.</p>
        </EmptyState>
      )}
      {ranking.status === "success" && rows.length > 0 && (
        <>
          <Card title={`Destinations for ${ranking.data.source_channel_name ?? ranking.data.source_channel_id}`}>
            <HorizontalBarChart
              title="Audience Bridge Score by destination"
              unit="score"
              bars={rows.map((r) => ({ key: r.destination_channel_id, label: `${r.rank ?? "–"}. ${r.destination_channel_name ?? r.destination_channel_id}`, value: r.audience_bridge_score }))}
            />
            <TableWrap label="Ranked destinations">
              <table className="table">
                <caption className="sr-only">Ranked destination channels with score components</caption>
                <thead>
                  <tr>
                    <th scope="col">Rank</th>
                    <th scope="col">Destination</th>
                    <th scope="col" title="(diffusion + topic) × confidence">Bridge score</th>
                    <th scope="col" title="w_diffusion × normalized PPR diffusion (structural connectivity)">Diffusion</th>
                    <th scope="col" title="w_topic × normalized topic similarity">Topic</th>
                    <th scope="col" title="Shared-commenter evidence × topic coverage">Confidence</th>
                    <th scope="col">Status</th>
                    <th scope="col">
                      <span className="sr-only">Evidence</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.destination_channel_id}>
                      <td>{r.rank ?? "—"}</td>
                      <td>{r.destination_channel_name ?? r.destination_channel_id}</td>
                      <td className="num">{num(r.audience_bridge_score, 4)}</td>
                      <td className="num">{num(r.diffusion_component)}</td>
                      <td className="num">{num(r.topic_component)}</td>
                      <td className="num">{num(r.confidence_component)}</td>
                      <td>{r.score_status === "ok" ? "ok" : r.score_status}</td>
                      <td>
                        <Link to={`/explainability?source=${encodeURIComponent(ranking.data.source_channel_id)}&destination=${encodeURIComponent(r.destination_channel_id)}`}>
                          Evidence
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <Pager total={ranking.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
          </Card>
          <Provenance snapshotId={ranking.data.snapshot_id} experimentId={ranking.data.experiment_id} />
        </>
      )}
    </>
  );
}
