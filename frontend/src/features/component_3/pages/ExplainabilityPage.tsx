import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ComponentBar } from "../../../components/charts/BarChart";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { ChannelAvatar } from "../../../components/common/ChannelAvatar";
import { Icon } from "../../../components/common/Icon";
import { Badge, KeyValues, Select, type Tone } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, isNoBridgeEvidence, label, NO_EVIDENCE_TITLE, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { channelName, useResearch } from "../ResearchContext";
import type { BridgePairResponse, EvidenceState } from "../types";

const STATE_TEXT: Record<string, [Tone, string, string]> = {
  observed: ["ok", "Observed", "Evidence exists for this pair."],
  zero: ["neutral", "Zero", "Both channels were observed; the value is genuinely 0."],
  insufficient_coverage: ["warn", "Insufficient coverage", "A channel has no stored videos or commenters, so absence is not informative."],
  missing: ["bad", "Missing", "The input needed for this evidence is not available."],
  not_used: ["neutral", "Not used", "This scoring experiment has no embedding component."],
};

/** Plain-language reading of the stored values. Wording stays descriptive: no migration, growth or causal claims. */
function interpretation(p: BridgePairResponse): string[] {
  const b = p.score_breakdown;
  const src = p.source_channel_name ?? p.source_channel_id, dst = p.destination_channel_name ?? p.destination_channel_id;
  const out: string[] = [];
  if (p.audience_bridge_score === 0) {
    out.push(`There is no bridge evidence between ${src} and ${dst}: they share no public commenters, so the score is 0 and the pair is not ranked (its listed position is only a tie-break).`);
  } else if (p.rank !== null && p.ranking_context) {
    out.push(`Within the observed public interaction data, ${dst} ranks ${p.rank} of ${p.ranking_context.scored_destinations} scored destinations for ${src}.`);
  }
  const parts = ([["structural connectivity (diffusion)", b.diffusion_component], ["learned graph similarity (embedding)", b.embedding_component],
    ["semantic content similarity (topic)", b.topic_component]] as [string, number | null][]).filter(([, v]) => v !== null) as [string, number][];
  if (parts.length) {
    const top = Math.max(...parts.map(([, v]) => v));
    const leaders = parts.filter(([, v]) => Math.abs(v - top) < 1e-9).map(([n]) => n);
    out.push(leaders.length === 1
      ? `The largest contribution to the base score comes from ${leaders[0]} (${top.toFixed(3)} of ${num(b.base_score)}).`
      : `${leaders.join(" and ").replace(/^./, (c) => c.toUpperCase())} contribute equally and most to the base score (${top.toFixed(3)} each, of ${num(b.base_score)}).`);
  }
  if (b.confidence_component !== null) {
    out.push(b.confidence_component >= 0.8
      ? `Shared-commenter evidence and topic coverage support the score (confidence ${num(b.confidence_component)}).`
      : b.confidence_component < 0.5
        ? `Limited shared-commenter evidence or topic coverage lowers the score (confidence ${num(b.confidence_component)}).`
        : `The evidence moderately supports the score (confidence ${num(b.confidence_component)}).`);
  }
  out.push("This pair shows observed audience affinity within public comment data. It is a research signal: it does not show audience migration, subscriber transfer or future growth.");
  return out;
}

/** Visual decomposition: components (weight × normalised signal) sum to the base score, which the
 * confidence multiplies into the final stored score. Only stored values are shown. */
function DecompositionFlow({ p }: { p: BridgePairResponse }) {
  const b = p.score_breakdown;
  const parts: [string, number | null, string][] = [
    ["Diffusion", b.diffusion_component, `${num(b.w_diffusion, 2)} × ${num(b.normalized_diffusion)}`],
    ...(b.w_embedding > 0 ? [["Embedding", b.embedding_component, `${num(b.w_embedding, 2)} × ${num(b.normalized_embedding_similarity)}`] as [string, number | null, string]] : []),
    ["Topic", b.topic_component, `${num(b.w_topic, 2)} × ${num(b.normalized_topic_similarity)}`],
  ];
  return (
    <figure className="xflow" aria-label="Score decomposition flow">
      <div className="xflow__parts">
        {parts.map(([name, v, how]) => (
          <div key={name} className="xflow__node xflow__node--part">
            <span>{name}</span><strong>{num(v)}</strong><small>{how}</small>
          </div>
        ))}
      </div>
      <span className="xflow__op" aria-hidden="true">Σ →</span>
      <div className="xflow__node"><span>Base score</span><strong>{num(b.base_score)}</strong><small>sum of components</small></div>
      <span className="xflow__op" aria-hidden="true">× →</span>
      <div className="xflow__node"><span>Confidence</span><strong>{num(b.confidence_component)}</strong><small>evidence {num(b.evidence_confidence, 2)} × coverage {num(b.topic_coverage_confidence, 2)}</small></div>
      <span className="xflow__op" aria-hidden="true">=</span>
      <div className="xflow__node xflow__node--final"><span>Audience Bridge Score</span><strong>{num(p.audience_bridge_score)}</strong><small>stored, directional</small></div>
      <figcaption className="sr-only">
        {parts.map(([n, v]) => `${n} ${num(v)}`).join(" plus ")} gives base score {num(b.base_score)}; multiplied by confidence {num(b.confidence_component)} gives {num(p.audience_bridge_score)}.
      </figcaption>
    </figure>
  );
}

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
  // with no pair chosen, open on the strongest stored bridge
  const top = useApi((s) => component3Api.topBridges({ snapshotId, experimentId }, 1, s), [snapshotId, experimentId], !source && !destination);
  useEffect(() => {
    const b = top.status === "success" ? top.data.items[0] : undefined;
    if (!source && !destination && b?.audience_bridge_score) {
      setParams({ source: b.source_channel_id, destination: b.destination_channel_id }, { replace: true });
    }
  }, [top, source, destination, setParams]);
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

  const p = pair.status === "success" ? pair.data : null;
  const b = p?.score_breakdown;
  const e = p?.evidence_summary ?? null;
  const order = list.map((c) => c.channel_id);
  const swap = () => setParams({ source: destination, destination: source });
  const score = p?.audience_bridge_score ?? null;
  const R = 52, C = 2 * Math.PI * R;
  const evidenceRows: { k: string; v: React.ReactNode; state: EvidenceState | null; icon: string }[] = e ? [
    { k: "Shared commenters", v: int(e.shared_commenters), state: e.shared_commenter_state, icon: "users" },
    { k: "Jaccard overlap", v: num(e.jaccard_similarity, 4), state: null, icon: "venn" },
    { k: "Share of source commenters also on destination", v: pct(e.directional_overlap_source_to_destination, 1), state: null, icon: "route" },
    { k: "Comments by shared commenters (source / destination)", v: `${int(e.shared_comments_on_source)} / ${int(e.shared_comments_on_destination)}`, state: e.video_coverage_state, icon: "comment" },
    { k: "Video coverage (source / destination)", v: `${pct(e.source_video_coverage)} / ${pct(e.destination_video_coverage)}`, state: null, icon: "play" },
    { k: "Active days of shared commenters", v: int(e.shared_active_days), state: e.temporal_state, icon: "overview" },
    { k: "First / last shared comment", v: `${date(e.shared_first_comment_at)} / ${date(e.shared_last_comment_at)}`, state: null, icon: "flow" },
    { k: "Topic similarity (raw cosine)", v: num(e.topic_similarity), state: e.topic_state, icon: "tag" },
    { k: "Channel-embedding similarity (raw cosine)", v: num(e.embedding_similarity), state: e.embedding_state, icon: "neural" },
  ] : [];

  return (
    <div className="gx">
      <section className="xhero gx__hero" aria-label="Explainability">
        <span className="gx__mark gx__mark--xpl" aria-hidden="true"><Icon name="explain" size={32} /></span>
        <div className="xhero__id">
          <h1>Why this score?</h1>
          <p>How a pair's Audience Bridge Score is built and the evidence behind it.</p>
          <p className="tx-note">{LIMITATIONS}</p>
        </div>
      </section>

      <section className="xp-pick" aria-label="Choose a pair">
        <div className="xp-pick__side">
          <span className="xp-pick__role">Source</span>
          <Select id="xpl-source" label="Source channel" value={source} placeholder="Select…" disabled={!list.length}
            options={list.map((c) => ({ value: c.channel_id, label: c.channel_name ?? c.channel_id }))} onChange={(v) => set("source", v)} />
        </div>
        <button type="button" className="xp-pick__swap" onClick={swap} disabled={!ready} aria-label="Swap direction" title="Swap direction">⇄</button>
        <div className="xp-pick__side">
          <span className="xp-pick__role">Destination</span>
          <Select id="xpl-destination" label="Destination channel" value={destination} placeholder="Select…" disabled={!list.length || !source}
            options={list.filter((c) => c.channel_id !== source).map((c) => ({ value: c.channel_id, label: c.channel_name ?? c.channel_id }))}
            onChange={(v) => set("destination", v)} />
        </div>
        {channels.status === "error" && <ErrorState error={channels.error} onRetry={channels.reload} what="Channels" />}
      </section>

      {!ready && <EmptyState title="Select a source and a destination channel." />}
      {pair.status === "loading" && <Loading variant="block" label="Loading explanation…" />}
      {pair.status === "error" && <ErrorState error={pair.error} onRetry={pair.reload} what="Explanation" />}
      {p && b && (
        <>
          <section className="xp-hero" aria-label="Pair summary">
            <div className="xp-hero__pair">
              <div className="xp-hero__ch">
                <ChannelAvatar id={p.source_channel_id} name={p.source_channel_name} order={order} size={70} />
                <span>Source</span><b>{p.source_channel_name ?? p.source_channel_id}</b>
              </div>
              <div className="xp-hero__arrow" aria-hidden="true"><i /><span>directional</span></div>
              <div className="xp-hero__ch">
                <ChannelAvatar id={p.destination_channel_id} name={p.destination_channel_name} order={order} size={70} />
                <span>Destination</span><b>{p.destination_channel_name ?? p.destination_channel_id}</b>
              </div>
            </div>
            <svg className="xp-hero__ring" viewBox="0 0 130 130" role="img" aria-label={`Audience Bridge Score ${num(score, 4)}`}>
              <circle cx={65} cy={65} r={R} className="ring__track" />
              <circle cx={65} cy={65} r={R} className="ring__value" strokeDasharray={`${C * Math.max(0, Math.min(1, score ?? 0))} ${C}`} transform="rotate(-90 65 65)" />
              <text x={65} y={68} textAnchor="middle" className="ring__num">{num(score, 4)}</text>
              <text x={65} y={86} textAnchor="middle" className="ring__cap">bridge score</text>
            </svg>
            <ul className="xp-hero__facts">
              {!isNoBridgeEvidence(score)
                ? <li><span>Rank</span><b>{p.rank === null ? "—" : `#${p.rank}`}</b><small>{p.ranking_context ? `of ${int(p.ranking_context.scored_destinations)} scored destinations` : ""}</small></li>
                : <li title={NO_EVIDENCE_TITLE}><span>Rank</span><b>—</b><small>no bridge evidence</small></li>}
              <li><span>Confidence</span><b>{num(b.confidence_component)}</b><small>evidence × topic coverage</small></li>
              <li><span>Shared commenters</span><b>{int(b.shared_commenters)}</b><small>aggregate count</small></li>
            </ul>
            {p.score_status !== "ok" && <p><Badge tone="warn">{p.score_status}</Badge></p>}
          </section>

          <section className="xblock" aria-label="How the score is built">
            <header className="xblock__head"><div><h3>How the score is built</h3><p>Weighted components form the base score; confidence scales it.</p></div></header>
            <DecompositionFlow p={p} />
          </section>

          <div className="xgrid xgrid--2">
            <section className="xblock" aria-label="Interpretation">
              <header className="xblock__head"><div><h3>What it means</h3><p>Generated from the stored values.</p></div></header>
              <ul className="xp-insights">
                {interpretation(p).map((t, i) => (
                  <li key={t}><span className="xp-insights__icon"><Icon name={["bridges", "graph", "evaluation", "explain"][i % 4]} size={16} /></span><p>{t}</p></li>
                ))}
              </ul>
            </section>
            <section className="xblock" aria-label="Ranking context">
              <header className="xblock__head"><div><h3>Ranking context</h3><p>Where this destination sits among the source's scored destinations.</p></div></header>
              {isNoBridgeEvidence(score) ? (
                <p className="muted">No bridge evidence: this pair shares no public commenters, so it has no meaningful position in the ranking.</p>
              ) : p.ranking_context ? (
                <>
                  <div className="xp-rank">
                    {Array.from({ length: Math.min(60, p.ranking_context.scored_destinations ?? 0) }, (_, i) => (
                      <i key={i} className={i + 1 === p.rank ? "is-on" : ""} title={i + 1 === p.rank ? "this pair" : `rank ${i + 1}`} />
                    ))}
                  </div>
                  <ul className="xp-neigh">
                    <li><span>Next higher</span><b>{p.ranking_context.next_higher_destination_id ? channelName(list, p.ranking_context.next_higher_destination_id) : "—"}</b><em>{num(p.ranking_context.next_higher_score, 4)}</em></li>
                    <li className="is-self"><span>This pair</span><b>{p.destination_channel_name}</b><em>{num(score, 4)}</em></li>
                    <li><span>Next lower</span><b>{p.ranking_context.next_lower_destination_id ? channelName(list, p.ranking_context.next_lower_destination_id) : "—"}</b><em>{num(p.ranking_context.next_lower_score, 4)}</em></li>
                  </ul>
                  <p className="xnote">Candidates {int(p.ranking_context.candidate_destinations)} · score percentile among this source's destinations {pct(p.ranking_context.score_percentile)}</p>
                </>
              ) : <p className="muted">Ranking context comes with the explanation artifact.</p>}
            </section>
          </div>

          <section className="xblock" aria-label="Score decomposition">
            <header className="xblock__head"><div><h3>Exact values</h3><p>The stored numbers behind the flow above.</p></div></header>
            <div className="xp-values">
              <ComponentBar diffusion={b.diffusion_component} embedding={b.embedding_component} topic={b.topic_component} />
              <KeyValues
                rows={[
                  ["Diffusion contribution", `${num(b.diffusion_component)} = ${num(b.w_diffusion)} × ${num(b.normalized_diffusion)}`],
                  ["Embedding contribution", b.w_embedding > 0 ? `${num(b.embedding_component)} = ${num(b.w_embedding)} × ${num(b.normalized_embedding_similarity)} (${b.embedding_source})` : "not used in this experiment"],
                  ["Topic contribution", `${num(b.topic_component)} = ${num(b.w_topic)} × ${num(b.normalized_topic_similarity)}`],
                  ["Base score", num(b.base_score)],
                  ["Confidence adjustment", `× ${num(b.confidence_component)} (evidence ${num(b.evidence_confidence)} × topic coverage ${num(b.topic_coverage_confidence)})`],
                  ["Raw PPR diffusion", num(b.raw_diffusion_score, 6)],
                  ["Raw embedding cosine", num(b.raw_embedding_similarity)],
                  ["Raw topic similarity", num(b.raw_topic_similarity)],
                ]}
              />
            </div>
            <p className="xnote"><code>{b.formula}</code></p>
          </section>

          {p.explanation_status === "unavailable" ? (
            <EmptyState title="Explanation not available">
              <p>{p.explanation_detail ?? "No explanation artifact exists for this experiment."}</p>
              <p className="muted">The score above is the stored result; no explanation is generated in the dashboard.</p>
            </EmptyState>
          ) : (
            <>
              {p.explanation_outcome && p.explanation_outcome !== "complete" && <p><Badge tone="warn">Explanation {label(p.explanation_outcome)}</Badge></p>}
              <section className="xblock" aria-label="Explanation reasons">
                <header className="xblock__head"><div><h3>Explanation reasons</h3><p>Criteria the explanation step recorded as met for this pair.</p></div></header>
                {p.explanation_reasons.length === 0 ? <p className="muted">No reason criterion was met for this pair.</p> : (
                  <ul className="xp-reasons">
                    {p.explanation_reasons.map((r) => (
                      <li key={r.reason_code}>
                        <span className="xp-reasons__tick" aria-hidden="true">✓</span>
                        <div>
                          <b>{label(r.reason_code)}</b>
                          <p>{r.reason_text}</p>
                          <small>Criterion: {r.criterion}</small>
                        </div>
                        {r.value !== null && (
                          <span className="xp-reasons__val">
                            <b>{num(r.value)}</b>
                            {r.threshold !== null && <small>threshold {num(r.threshold)}</small>}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <div className="xgrid xp-split">
                <section className="xblock" aria-label="Aggregate evidence">
                  <header className="xblock__head"><div><h3>Aggregate evidence</h3><p>Aggregate counts behind the confidence.</p></div></header>
                  {e === null ? <p className="muted">No evidence row for this pair.</p> : (
                    <ul className="xp-evidence">
                      {evidenceRows.map((r) => (
                        <li key={r.k}>
                          <span className="xp-evidence__icon"><Icon name={r.icon} size={15} /></span>
                          <span className="xp-evidence__k">{r.k}</span>
                          <b className="num">{r.v}</b>
                          <span>{r.state && <StateBadge state={r.state} />}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <section className="xblock" aria-label="Uncertainty">
                  <header className="xblock__head"><div><h3>Uncertainty</h3><p>Caveats recorded with this explanation.</p></div></header>
                  {p.uncertainty_notes.length ? (
                    <ul className="xp-notes">{p.uncertainty_notes.map((n) => <li key={n}><span aria-hidden="true">!</span>{n}</li>)}</ul>
                  ) : <p className="muted">No uncertainty note recorded.</p>}
                </section>
              </div>
            </>
          )}
          <Provenance snapshotId={p.snapshot_id} experimentId={p.experiment_id} extra={p.explanation_id ? `Explanation ${p.explanation_id}` : "No explanation artifact"} />
        </>
      )}
    </div>
  );
}
