/**
 * Audience Bridge explorer: a card graph around one source channel (inbound channels → source →
 * outbound destinations) and the inspection panel of the selected directed pair. The layout is fixed
 * (rows of cards), so the same data always gives the same picture. All values are stored API values;
 * the controls only choose which stored pairs are drawn.
 */
import { ChannelAvatar } from "../../components/common/ChannelAvatar";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowLane, type FlowNode } from "../../components/charts/FlowCanvas";
import { ScoreBreakdown } from "../../components/charts/ScoreBreakdown";
import { EmptyState, ErrorState, Loading } from "../../components/common/States";
import { useApi } from "../../hooks/useApi";
import { int, isNoBridgeEvidence, NO_EVIDENCE_TITLE, num, pct } from "../../utils/format";
import { component3Api } from "./api";
import { useResearch } from "./ResearchContext";
import type { BridgePairRow } from "./types";

const TOPK = [3, 5];
const W = 1220, LEFT = 170, CARD_W = 184, CARD_H = 92, GAP = 24, SRC_W = 260, SRC_H = 104;

/** Strength band of a stored score (used for the connector colour; the legend states the bands). */
const band = (s: number) => (s >= 0.6 ? "#1d4ed8" : s >= 0.3 ? "#60a5fa" : "#cbd5e1");

/** Inspection panel for one directed pair: stored score, decomposition and aggregate evidence. */
export function BridgeInspector({ source, destination }: { source: string; destination: string }) {
  const { snapshotId, experimentId } = useResearch();
  const pair = useApi((s) => component3Api.pair(source, destination, { snapshotId, experimentId }, s),
    [source, destination, snapshotId, experimentId], source !== "" && destination !== "" && source !== destination);
  if (pair.status === "loading" || pair.status === "idle") return <Loading label="Loading bridge…" variant="block" />;
  if (pair.status === "error") return <ErrorState error={pair.error} onRetry={pair.reload} what="This bridge" />;
  const p = pair.data, b = p.score_breakdown, e = p.evidence_summary;
  return (
    <div className="insp">
      <div className="insp__dir">
        <span className="insp__role">Source</span>
        <strong className="insp__ch"><ChannelAvatar id={p.source_channel_id} name={p.source_channel_name} size={24} />{p.source_channel_name ?? p.source_channel_id}</strong>
        <span className="insp__arrow" aria-hidden="true">↓</span>
        <span className="insp__role">Destination</span>
        <strong className="insp__ch"><ChannelAvatar id={p.destination_channel_id} name={p.destination_channel_name} size={24} />{p.destination_channel_name ?? p.destination_channel_id}</strong>
      </div>
      <div className="insp__nums">
        <div><span>Audience Bridge Score</span><strong>{num(p.audience_bridge_score, 3)}</strong></div>
        <div><span>Confidence</span><strong>{num(b.confidence_component, 3)}</strong></div>
        <div><span>Rank for source</span>{!isNoBridgeEvidence(p.audience_bridge_score)
          ? <strong>{p.rank ?? "—"}{p.ranking_context ? <small> / {int(p.ranking_context.scored_destinations)}</small> : null}</strong>
          : <strong title={NO_EVIDENCE_TITLE}>No bridge evidence</strong>}</div>
      </div>
      <ScoreBreakdown compact b={{ diffusion: b.diffusion_component, embedding: b.embedding_component, topic: b.topic_component,
        base: b.base_score, confidence: b.confidence_component, score: p.audience_bridge_score, embeddingUsed: b.w_embedding > 0 }} />
      <details className="insp__evidence" open>
        <summary>Supporting evidence (aggregate)</summary>
        {e === null ? <p className="muted small">No evidence row for this pair.</p> : (
          <dl>
            <div><dt>Shared commenters</dt><dd>{int(e.shared_commenters)}</dd></div>
            <div><dt>Interactions (source / destination)</dt><dd>{int(e.shared_comments_on_source)} / {int(e.shared_comments_on_destination)}</dd></div>
            <div><dt>Video coverage (source / destination)</dt><dd>{pct(e.source_video_coverage)} / {pct(e.destination_video_coverage)}</dd></div>
            <div><dt>Temporal support</dt><dd>{int(e.shared_active_days)} active days</dd></div>
            <div><dt>Data coverage (topic profiles)</dt><dd>{num(b.topic_coverage_confidence, 2)}</dd></div>
          </dl>
        )}
      </details>
      <p className="insp__note">The bridge score is directional (source → destination); topic similarity is symmetric.</p>
      <Link className="insp__link" to={`/explainability?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`}>Why this score? Full explanation →</Link>
    </div>
  );
}

function PairCard({ id, name, r }: { id: string; name: string; r: BridgePairRow }) {
  const s = r.audience_bridge_score ?? 0;
  return (
    <span className="bc">
      <span className="bc__title"><ChannelAvatar id={id} name={name} size={22} /><span className="bc__name">{name}</span></span>
      <span className="bc__meta">conf {num(r.confidence_component, 2)} · {int(r.shared_commenters)} shared</span>
      <span className="bc__foot">
        <span className="bc__bar" aria-hidden="true"><i style={{ width: `${Math.round(s * 100)}%` }} /></span>
        <strong className="bc__score">{num(r.audience_bridge_score, 3)}</strong>
      </span>
    </span>
  );
}

/** x positions of k cards centred on the canvas */
const row = (k: number) => {
  const total = k * CARD_W + (k - 1) * GAP;
  return Array.from({ length: k }, (_, i) => LEFT + (W - LEFT - total) / 2 + i * (CARD_W + GAP));
};

export function BridgeExplorer({ pairs, source, destination, onSource, onPair }: {
  pairs: BridgePairRow[];
  source: string;
  destination: string;
  onSource: (id: string) => void;
  onPair: (source: string, destination: string) => void;
}) {
  const { snapshotId } = useResearch();
  const perf = useApi((s) => component3Api.dashboardChannels({ snapshotId }, s), [snapshotId]);
  const [topK, setTopK] = useState(5);
  const [hideLow, setHideLow] = useState(false);

  const positive = useMemo(() => pairs.filter((r) => (r.audience_bridge_score ?? 0) > 0), [pairs]);
  const channels = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of pairs) {
      m.set(r.source_channel_id, r.source_channel_name ?? r.source_channel_id);
      m.set(r.destination_channel_id, r.destination_channel_name ?? r.destination_channel_id);
    }
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [pairs]);
  // default source: the source of the strongest stored pair (pairs arrive ordered by score)
  const active = source || positive[0]?.source_channel_id || "";
  const name = (id: string) => channels.find(([c]) => c === id)?.[1] ?? id;
  const keep = (r: BridgePairRow) => !hideLow || (r.confidence_component ?? 0) >= 0.5;
  const outAll = positive.filter((r) => r.source_channel_id === active);
  const inAll = positive.filter((r) => r.destination_channel_id === active);
  const outbound = outAll.filter(keep).sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9)).slice(0, topK);
  const inbound = inAll.filter(keep).sort((a, b) => (b.audience_bridge_score ?? 0) - (a.audience_bridge_score ?? 0)).slice(0, topK);
  const perfRow = perf.status === "success" ? perf.data.items.find((c) => c.channel_id === active) : undefined;

  if (pairs.length === 0) return <EmptyState title="No bridge relationships are available for this snapshot." />;

  const isSel = (s: string, d: string) => s === source && d === destination;
  const srcX = LEFT + (W - LEFT - SRC_W) / 2, inY = 24, srcY = 250, outY = 470, H = outY + CARD_H + 26;
  const lanes: FlowLane[] = [
    { id: "in", title: "Inbound bridges", x: 12, y: inY - 14, w: W - 24, h: CARD_H + 28 },
    { id: "src", title: "Source", x: 12, y: srcY - 14, w: W - 24, h: SRC_H + 28 },
    { id: "out", title: "Outbound bridges", x: 12, y: outY - 14, w: W - 24, h: CARD_H + 28 },
  ];
  const nodes: FlowNode[] = [
    { id: "src", x: srcX, y: srcY, w: SRC_W, h: SRC_H, tone: "stored", label: `${name(active)}: selected source`,
      content: (
        <span className="bc bc--source">
          <span className="bc__kicker">Selected source</span>
          <span className="bc__title"><ChannelAvatar id={active} name={name(active)} size={28} /><span className="bc__name">{name(active)}</span></span>
          <span className="bc__meta">{perfRow ? `${int(perfRow.unique_commenters)} unique commenters · ${int(perfRow.videos)} videos` : "channel"}</span>
          <span className="bc__meta">{outAll.length} outbound · {inAll.length} inbound bridges</span>
        </span>
      ) },
    ...row(inbound.length).map((x, i): FlowNode => {
      const r = inbound[i];
      return { id: `in:${r.source_channel_id}`, x, y: inY, w: CARD_W, h: CARD_H, selected: isSel(r.source_channel_id, active),
        label: `${name(r.source_channel_id)} to ${name(active)}: score ${num(r.audience_bridge_score, 3)}, confidence ${num(r.confidence_component, 2)}`,
        content: <PairCard id={r.source_channel_id} name={name(r.source_channel_id)} r={r} /> };
    }),
    ...row(outbound.length).map((x, i): FlowNode => {
      const r = outbound[i];
      return { id: `out:${r.destination_channel_id}`, x, y: outY, w: CARD_W, h: CARD_H, selected: isSel(active, r.destination_channel_id),
        label: `${name(active)} to ${name(r.destination_channel_id)}: score ${num(r.audience_bridge_score, 3)}, confidence ${num(r.confidence_component, 2)}`,
        content: <PairCard id={r.destination_channel_id} name={name(r.destination_channel_id)} r={r} /> };
    }),
  ];
  // labels sit where the fanned-out connectors are furthest apart: near the cards, away from the source
  const edge = (from: string, to: string, r: BridgePairRow, labelAt: number): FlowEdge => {
    const s = r.audience_bridge_score ?? 0;
    return { from, to, color: band(s), width: 1.5 + 4 * s, dashed: (r.confidence_component ?? 0) < 0.5, label: s.toFixed(2), labelAt };
  };
  const edges: FlowEdge[] = [
    ...inbound.map((r) => edge(`in:${r.source_channel_id}`, "src", r, 0.22)),
    ...outbound.map((r) => edge("src", `out:${r.destination_channel_id}`, r, 0.8)),
  ];
  const select = (id: string) => {
    if (id.startsWith("out:")) onPair(active, id.slice(4));
    else if (id.startsWith("in:")) onPair(id.slice(3), active);
  };

  return (
    <div className="bx2">
      <div className="bx2__controls" role="group" aria-label="Graph controls">
        <label><span>Source channel</span>
          <select value={active} onChange={(e) => onSource(e.target.value)}>
            {channels.map(([id, n]) => <option key={id} value={id}>{n}</option>)}
          </select>
        </label>
        <label><span>Bridges per side</span>
          <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}>{TOPK.map((k) => <option key={k} value={k}>Top {k}</option>)}</select>
        </label>
        <label className="bx2__check"><input type="checkbox" checked={hideLow} onChange={(e) => setHideLow(e.target.checked)} /> Hide confidence below 0.5</label>
        <span className="bx2__count">{outbound.length} outbound · {inbound.length} inbound shown</span>
      </div>
      <div className="bx2__body">
        <div className="bx2__graph">
          <FlowCanvas width={W} height={H} nodes={nodes} edges={edges} lanes={lanes} onSelect={select} minScale={0.5}
            label={`Audience bridges of ${name(active)}`} />
          {outbound.length === 0 && inbound.length === 0 && <p className="muted small">No bridge with a positive score for this channel{hideLow ? " at this confidence" : ""}.</p>}
          <FlowLegend items={[
            { kind: "line", label: "Arrow: direction (source → destination)" },
            { kind: "dash", label: "Dashed: confidence below 0.5" },
            { kind: "dot", tone: "strong", label: "Score ≥ 0.6" },
            { kind: "dot", tone: "moderate", label: "0.3 – 0.6" },
            { kind: "dot", tone: "weak", label: "< 0.3" },
          ]} />
        </div>
        <aside className="bx2__inspector" aria-label="Selected bridge">
          {source && destination ? <BridgeInspector source={source} destination={destination} /> : (
            <EmptyState title="Select a card to inspect a bridge.">
              <p>Each card is a stored directed bridge. Its score, decomposition and evidence open here.</p>
            </EmptyState>
          )}
        </aside>
      </div>
    </div>
  );
}
