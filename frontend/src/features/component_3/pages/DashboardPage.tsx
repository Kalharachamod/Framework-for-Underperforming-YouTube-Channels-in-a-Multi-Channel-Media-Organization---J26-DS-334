import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BridgeTree } from "../../../components/charts/BridgeTree";
import { ScoreBreakdown } from "../../../components/charts/ScoreBreakdown";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Card } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, num } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { GraphSummaryResponse, ResearchStatusResponse } from "../types";

const DEPTHS = [3, 5, 8, 10];

type StepState = "available" | "missing" | "unknown";
/** The Component 3 method, in order, with the stored artifact that shows each step ran. */
function methodSteps(status: ResearchStatusResponse | null, graph: GraphSummaryResponse | null) {
  const art = (name: string): StepState => {
    const a = status?.artifacts.find((x) => x.name === name);
    return a ? (a.status === "available" ? "available" : "missing") : "unknown";
  };
  const reps = graph?.representations ?? [];
  const embed: StepState = reps.length ? (reps.some((r) => r.status === "available") ? "available" : "missing") : "unknown";
  const both = (a: StepState, b: StepState): StepState => (a === "available" && b === "available" ? "available" : a === "unknown" || b === "unknown" ? "unknown" : "missing");
  const abs = art("audience_bridge_scores");
  return [
    { key: "graph", label: "Heterogeneous graph", sub: "channels · videos · commenters · topics", state: art("heterogeneous_graph"), to: "/graph" },
    { key: "embed", label: "metapath2vec / HGT", sub: "graph representations", state: embed, to: "/graph" },
    { key: "ppr", label: "Personalized PageRank", sub: "diffusion from each source", state: art("ppr_diffusion"), to: "/graph" },
    { key: "topic", label: "Topic similarity", sub: "semantic channel profiles", state: art("topic_similarity"), to: "/topics" },
    { key: "conf", label: "Confidence weighting", sub: "evidence × topic coverage", state: abs, to: "/bridges" },
    { key: "abs", label: "Audience Bridge Score", sub: "base score × confidence", state: abs, to: "/bridges" },
    { key: "base", label: "Baseline comparison", sub: "Louvain · node2vec", state: both(art("baseline_louvain"), art("baseline_node2vec")), to: "/evaluation" },
    { key: "eval", label: "Evaluation", sub: "agreement · stability · robustness", state: art("evaluations"), to: "/evaluation" },
    { key: "xpl", label: "Explainability", sub: "decomposition · evidence", state: art("explanations"), to: "/explainability" },
  ];
}

export function DashboardPage() {
  const { snapshotId, experimentId, status } = useResearch();
  const c = { snapshotId, experimentId };
  const [params, setParams] = useSearchParams();
  const summary = useApi((s) => component3Api.dashboardSummary(c, s), [snapshotId]);
  const graph = useApi((s) => component3Api.graphSummary(c, s), [snapshotId]);
  const pairs = useApi((s) => component3Api.bridgePairs(c, s), [snapshotId, experimentId]);

  const items = useMemo(() => (pairs.status === "success" ? pairs.data.items : []), [pairs]);
  const sources = useMemo(() => {
    const seen = new Map<string, string>();
    for (const r of items) if (!seen.has(r.source_channel_id)) seen.set(r.source_channel_id, r.source_channel_name ?? r.source_channel_id);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [items]);
  const source = params.get("source") ?? items[0]?.source_channel_id ?? "";
  const depth = Number(params.get("depth") ?? 5);
  const outgoing = items.filter((r) => r.source_channel_id === source && r.audience_bridge_score !== null)
    .sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9));
  const shown = outgoing.slice(0, depth);
  const destination = params.get("destination") ?? shown[0]?.destination_channel_id ?? "";
  const sel = outgoing.find((r) => r.destination_channel_id === destination) ?? null;
  const update = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) if (v) next.set(k, v); else next.delete(k);
    setParams(next);
  };

  if (status.status === "success" && status.data.research_data === "missing") {
    return <EmptyState title="No research data available for this snapshot."><p>Run the collection pipeline and create a research snapshot first.</p></EmptyState>;
  }
  const s = summary.status === "success" ? summary.data : null;
  const g = graph.status === "success" ? graph.data : null;
  const steps = methodSteps(status.status === "success" ? status.data : null, g);

  return (
    <div className="ov">
      <header className="ov-hero">
        <p className="ov-hero__eyebrow">Component 3 · Research overview</p>
        <h1>Cross-Channel Audience Intelligence</h1>
        <p className="ov-hero__lead">Identify potential cross-channel audience bridges using heterogeneous graph learning, diffusion,
          semantic similarity and confidence-weighted scoring.</p>
      </header>

      {summary.status === "error" ? <ErrorState error={summary.error} onRetry={summary.reload} /> : (
        <section className="rs-strip rs-strip--status" aria-label="Research status">
          <div className="rs-strip__cell"><span>Snapshot</span><strong>{s ? date(s.extracted_at).slice(0, 10) : "—"}</strong><small className="mono">{s?.snapshot_id ?? ""}</small></div>
          <div className="rs-strip__cell"><span>Channels</span><strong>{s ? int(s.channels) : "—"}</strong></div>
          <div className="rs-strip__cell"><span>Videos</span><strong>{s ? int(s.videos) : "—"}</strong></div>
          <div className="rs-strip__cell"><span>Comments</span><strong>{s ? int(s.collected_comments) : "—"}</strong><small>collected</small></div>
          <div className="rs-strip__cell"><span>Graph nodes</span><strong>{g ? int(g.total_nodes) : "—"}</strong></div>
          <div className="rs-strip__cell"><span>Graph edges</span><strong>{g ? int(g.total_edges) : "—"}</strong></div>
          <div className="rs-strip__cell"><span>Experiment</span><strong className="rs-strip__text">{pairs.status === "success" ? pairs.data.experiment_id : "—"}</strong><small>scoring run</small></div>
        </section>
      )}

      <section className="ov-method" aria-label="Method">
        <ol>
          {steps.map((st, i) => (
            <li key={st.key} className={`ov-method__step is-${st.state}`}>
              <Link to={st.to}>
                <span className="ov-method__n">{String(i + 1).padStart(2, "0")}</span>
                <span className="ov-method__label">{st.label}</span>
                <span className="ov-method__sub">{st.sub}</span>
                <span className="ov-method__state">{st.state === "available" ? "stored" : st.state === "missing" ? "not run" : "—"}</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <Card title="Bridge explorer" info="Stored Audience Bridge Scores of the selected scoring run. Ribbon width follows the score and opacity the confidence. A potential bridge is a ranking signal, not observed audience movement.">
        {pairs.status === "loading" && <Loading label="Loading scored pairs…" />}
        {pairs.status === "error" && <ErrorState error={pairs.error} onRetry={pairs.reload} />}
        {pairs.status === "success" && (items.length === 0 ? <EmptyState title="No research data available for this snapshot." /> : (
          <>
            <div className="ov-controls">
              <label><span>Source channel</span>
                <select value={source} onChange={(e) => update({ source: e.target.value, destination: undefined })}>
                  {sources.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
              </label>
              <label><span>Destination</span>
                <select value={destination} onChange={(e) => update({ destination: e.target.value })}>
                  {outgoing.map((r) => <option key={r.destination_channel_id} value={r.destination_channel_id}>#{r.rank} {r.destination_channel_name}</option>)}
                </select>
              </label>
              <label><span>Ranking depth</span>
                <select value={depth} onChange={(e) => update({ depth: e.target.value })}>
                  {DEPTHS.map((d) => <option key={d} value={d}>Top {d}</option>)}
                </select>
              </label>
            </div>
            <div className="ov-explorer">
              {outgoing.length === 0 ? <EmptyState title="This source has no scored destination." /> : (
                <div className="ov-tree">
                  <BridgeTree source={{ id: source, label: sources.find(([id]) => id === source)?.[1] ?? source }}
                    subtitle={`Top ${shown.length} of ${outgoing.length} scored destinations`}
                    targets={shown.map((r) => ({ id: r.destination_channel_id, label: r.destination_channel_name ?? r.destination_channel_id,
                      score: r.audience_bridge_score, confidence: r.confidence_component, rank: r.rank, shared: r.shared_commenters }))}
                    selected={destination} onSelect={(d) => update({ destination: d })} />
                </div>
              )}
              <aside className="ov-readout" aria-label="Selected bridge">
                {sel ? (
                  <>
                    <p className="ov-readout__pair">{sel.source_channel_name} <span aria-hidden="true">→</span> {sel.destination_channel_name}</p>
                    <div className="ov-readout__nums">
                      <div><span>Score</span><strong>{num(sel.audience_bridge_score, 3)}</strong></div>
                      <div><span>Confidence</span><strong>{num(sel.confidence_component, 3)}</strong></div>
                      <div><span>Shared commenters</span><strong>{int(sel.shared_commenters)}</strong></div>
                    </div>
                    <ScoreBreakdown compact b={{ diffusion: sel.diffusion_component, embedding: sel.embedding_component, topic: sel.topic_component,
                      base: sel.base_score, confidence: sel.confidence_component, score: sel.audience_bridge_score }} />
                    <Link className="ov-readout__link" to={`/bridges?source=${encodeURIComponent(sel.source_channel_id)}&destination=${encodeURIComponent(sel.destination_channel_id)}`}>Analyse this bridge →</Link>
                  </>
                ) : <EmptyState title="Select a destination." />}
              </aside>
            </div>
          </>
        ))}
      </Card>

      <div className="grid grid--2">
        <Card title="Strongest potential bridges" actions={<Link to="/bridges" className="ws-link">All pairs</Link>}>
          {pairs.status === "success" && (
            <ol className="ov-top">
              {items.filter((r) => r.audience_bridge_score !== null).slice(0, 6).map((r, i) => (
                <li key={`${r.source_channel_id}-${r.destination_channel_id}`}>
                  <span className="ov-top__n">{i + 1}</span>
                  <Link to={`/bridges?source=${encodeURIComponent(r.source_channel_id)}&destination=${encodeURIComponent(r.destination_channel_id)}`}>
                    {r.source_channel_name} → {r.destination_channel_name}
                  </Link>
                  <span className="ov-top__score">{num(r.audience_bridge_score, 3)}</span>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <Card title="Most connected channels" info="Channels sharing at least one commenter with the most other research channels (aggregate counts)." actions={<Link to="/graph" className="ws-link">Graph intelligence</Link>}>
          {graph.status === "loading" && <Loading />}
          {graph.status === "error" && <ErrorState error={graph.error} />}
          {g && (
            <ol className="ov-top">
              {g.channel_connectivity.slice(0, 6).map((ch, i) => (
                <li key={ch.channel_id}>
                  <span className="ov-top__n">{i + 1}</span>
                  <Link to={`/channels?channel=${encodeURIComponent(ch.channel_id)}`}>{ch.channel_name ?? ch.channel_id}</Link>
                  <span className="ov-top__score">{int(ch.connected_channels)} channels</span>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <footer className="ws-foot">
        <p>{LIMITATIONS}</p>
        <Provenance snapshotId={s?.snapshot_id ?? null} experimentId={pairs.status === "success" ? pairs.data.experiment_id : null} />
      </footer>
    </div>
  );
}
