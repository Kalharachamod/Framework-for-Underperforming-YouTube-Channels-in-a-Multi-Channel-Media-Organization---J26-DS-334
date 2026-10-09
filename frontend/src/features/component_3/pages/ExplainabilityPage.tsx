import { useSearchParams } from "react-router-dom";
import { ComponentBar } from "../../../components/charts/BarChart";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, Notice, PageHeader, Select, TableWrap, type Tone } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { channelName, useResearch } from "../ResearchContext";
import type { EvidenceState } from "../types";

const STATE_TEXT: Record<string, [Tone, string, string]> = {
  observed: ["ok", "Observed", "Evidence exists for this pair."],
  zero: ["neutral", "Zero", "Both channels were observed; the value is genuinely 0."],
  insufficient_coverage: ["warn", "Insufficient coverage", "A channel has no stored videos or commenters, so absence is not informative."],
  missing: ["bad", "Missing", "The input needed for this evidence is not available."],
};

function StateBadge({ state }: { state: EvidenceState }) {
  const [tone, text, help] = STATE_TEXT[state] ?? ["neutral", label(state), ""];
  return (
    <span title={help}>
      <Badge tone={tone}>{text}</Badge>
    </span>
  );
}

export function ExplainabilityPage() {
  const { channels, snapshotId, experimentId } = useResearch();
  const [params, setParams] = useSearchParams();
  const source = params.get("source") ?? "";
  const destination = params.get("destination") ?? "";
  const ready = source !== "" && destination !== "" && source !== destination;
  const pair = useApi(
    (s) => component3Api.pair(source, destination, { snapshotId, experimentId }, s),
    [source, destination, snapshotId, experimentId],
    ready,
  );
  const list = channels.status === "success" ? channels.data.items : [];
  const set = (key: "source" | "destination", v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(key, v);
    else next.delete(key);
    if (key === "source" && v === destination) next.delete("destination");
    setParams(next);
  };

  return (
    <>
      <PageHeader title="Explainability" description="Why the scoring method ranked a destination: score decomposition, aggregate evidence, reasons and uncertainty." />
      <Notice>{LIMITATIONS} Explanations describe the method's behaviour; they are not empirical validation.</Notice>
      <Card>
        <div className="controls">
          <Select id="xpl-source" label="Source channel" value={source} placeholder="Select…" disabled={!list.length}
            options={list.map((c) => ({ value: c.channel_id, label: c.channel_name ?? c.channel_id }))} onChange={(v) => set("source", v)} />
          <Select id="xpl-destination" label="Destination channel" value={destination} placeholder="Select…" disabled={!list.length || !source}
            options={list.filter((c) => c.channel_id !== source).map((c) => ({ value: c.channel_id, label: c.channel_name ?? c.channel_id }))}
            onChange={(v) => set("destination", v)} />
        </div>
        {channels.status === "error" && <ErrorState error={channels.error} />}
      </Card>

      {!ready && <EmptyState title="Select a source and a destination channel." />}
      {pair.status === "loading" && <Loading label="Loading explanation…" />}
      {pair.status === "error" && <ErrorState error={pair.error} onRetry={pair.reload} />}
      {pair.status === "success" && (() => {
        const p = pair.data;
        const b = p.score_breakdown;
        const e = p.evidence_summary;
        return (
          <>
            <div className="grid grid--2">
              <Card title={`${p.source_channel_name ?? p.source_channel_id} → ${p.destination_channel_name ?? p.destination_channel_id}`}>
                <p className="score">
                  <span className="score__value">{num(p.audience_bridge_score, 4)}</span>
                  <span className="muted"> Audience Bridge Score{p.rank !== null ? ` · rank ${p.rank}` : ""}</span>
                </p>
                {p.score_status !== "ok" && <p><Badge tone="warn">{p.score_status}</Badge></p>}
                <ComponentBar diffusion={b.diffusion_component} topic={b.topic_component} />
                <KeyValues
                  rows={[
                    ["Diffusion contribution", `${num(b.diffusion_component)} = ${b.w_diffusion} × ${num(b.normalized_diffusion)}`],
                    ["Topic contribution", `${num(b.topic_component)} = ${b.w_topic} × ${num(b.normalized_topic_similarity)}`],
                    ["Base score", num(b.base_score)],
                    ["Confidence adjustment", `× ${num(b.confidence_component)} (evidence ${num(b.evidence_confidence)} × topic coverage ${num(b.topic_coverage_confidence)})`],
                    ["Raw PPR diffusion", num(b.raw_diffusion_score, 6)],
                    ["Raw topic similarity", num(b.raw_topic_similarity)],
                  ]}
                />
                <p className="muted"><code>{b.formula}</code></p>
              </Card>
              <Card title="Ranking context">
                {p.ranking_context ? (
                  <KeyValues
                    rows={[
                      ["Rank", p.rank === null ? "—" : `${p.rank} of ${int(p.ranking_context.scored_destinations)} scored destinations`],
                      ["Candidates", int(p.ranking_context.candidate_destinations)],
                      ["Score percentile (among this source's destinations)", pct(p.ranking_context.score_percentile)],
                      ["Next higher", p.ranking_context.next_higher_destination_id ? `${channelName(list, p.ranking_context.next_higher_destination_id)} (${num(p.ranking_context.next_higher_score, 4)})` : "—"],
                      ["Next lower", p.ranking_context.next_lower_destination_id ? `${channelName(list, p.ranking_context.next_lower_destination_id)} (${num(p.ranking_context.next_lower_score, 4)})` : "—"],
                    ]}
                  />
                ) : (
                  <p className="muted">Ranking context comes with the explanation artifact.</p>
                )}
              </Card>
            </div>

            {p.explanation_status === "unavailable" ? (
              <EmptyState title="Explanation not available">
                <p>{p.explanation_detail ?? "No explanation artifact exists for this experiment."}</p>
                <p className="muted">The score above is the stored result; no explanation is generated in the dashboard.</p>
              </EmptyState>
            ) : (
              <>
                {p.explanation_outcome && p.explanation_outcome !== "complete" && (
                  <p><Badge tone="warn">Explanation {label(p.explanation_outcome)}</Badge></p>
                )}
                <Card title="Explanation reasons">
                  {p.explanation_reasons.length === 0 ? (
                    <p className="muted">No reason criterion was met for this pair.</p>
                  ) : (
                    <ul className="reasons">
                      {p.explanation_reasons.map((r) => (
                        <li key={r.reason_code}>
                          <strong>{label(r.reason_code)}</strong>: {r.reason_text}
                          <span className="muted"> Criterion: {r.criterion}{r.value !== null ? ` · value ${num(r.value)}` : ""}{r.threshold !== null ? ` · threshold ${num(r.threshold)}` : ""}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
                <Card title="Aggregate evidence">
                  {e === null ? (
                    <p className="muted">No evidence row for this pair.</p>
                  ) : (
                    <TableWrap label="Evidence">
                      <table className="table">
                        <thead>
                          <tr><th scope="col">Evidence</th><th scope="col">Value</th><th scope="col">State</th></tr>
                        </thead>
                        <tbody>
                          <tr><td>Shared commenters</td><td className="num">{int(e.shared_commenters)}</td><td rowSpan={3}><StateBadge state={e.shared_commenter_state} /></td></tr>
                          <tr><td>Jaccard overlap</td><td className="num">{num(e.jaccard_similarity, 4)}</td></tr>
                          <tr><td>Share of source commenters also on destination</td><td className="num">{pct(e.directional_overlap_source_to_destination, 1)}</td></tr>
                          <tr><td>Comments by shared commenters (source / destination)</td><td className="num">{int(e.shared_comments_on_source)} / {int(e.shared_comments_on_destination)}</td><td rowSpan={2}><StateBadge state={e.video_coverage_state} /></td></tr>
                          <tr><td>Video coverage (source / destination)</td><td className="num">{pct(e.source_video_coverage)} / {pct(e.destination_video_coverage)}</td></tr>
                          <tr><td>Active days of shared commenters</td><td className="num">{int(e.shared_active_days)}</td><td rowSpan={2}><StateBadge state={e.temporal_state} /></td></tr>
                          <tr><td>First / last shared comment</td><td>{date(e.shared_first_comment_at)} / {date(e.shared_last_comment_at)}</td></tr>
                          <tr><td>Topic similarity (raw cosine)</td><td className="num">{num(e.topic_similarity)}</td><td><StateBadge state={e.topic_state} /></td></tr>
                        </tbody>
                      </table>
                    </TableWrap>
                  )}
                  <p className="muted">States: observed · zero (observed, value 0) · insufficient coverage (absence not informative) · missing (input unavailable).</p>
                </Card>
                <Card title="Uncertainty">
                  {p.uncertainty_notes.length ? (
                    <ul>{p.uncertainty_notes.map((n) => <li key={n}>{n}</li>)}</ul>
                  ) : (
                    <p className="muted">No uncertainty note recorded.</p>
                  )}
                </Card>
              </>
            )}
            <Provenance snapshotId={p.snapshot_id} experimentId={p.experiment_id} extra={p.explanation_id ? `Explanation ${p.explanation_id}` : "No explanation artifact"} />
          </>
        );
      })()}
    </>
  );
}
