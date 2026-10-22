import { Link, useSearchParams } from "react-router-dom";
import { ChannelAvatar } from "../../../components/common/ChannelAvatar";
import { Gauge } from "../../../components/charts/Gauge";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowLane, type FlowNode } from "../../../components/charts/FlowCanvas";
import { Histogram } from "../../../components/charts/Matrix";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Icon } from "../../../components/common/Icon";
import { Badge } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { DiffusionSummary, GraphSummaryResponse, Representation, Scalar } from "../types";

const TYPE_ORDER = ["channel", "video", "commenter", "topic"];
const NODE_COLORS: Record<string, string> = { commenter: "#93c5fd", video: "#3b82f6", channel: "#1e3a8a", topic: "#94a3b8" };
const scalar = (v: Scalar | undefined) => (v === null || v === undefined ? "—" : typeof v === "number"
  ? (Number.isInteger(v) ? int(v) : Math.abs(v) < 1e-3 ? v.toExponential(2) : String(Number(v.toPrecision(6)))) : String(v));
const compactN = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);

/** Channel overlap graph components drawn as clusters of dots (one dot per channel). */
function Components({ sizes }: { sizes: number[] }) {
  const isolated = sizes.filter((c) => c === 1).length;
  return (
    <div className="comps" role="img" aria-label={`${sizes.length} connected components; sizes ${sizes.join(", ")}`}>
      <div className="comps__row">
        {sizes.map((n, i) => (
          <span key={i} className={`comps__cluster${n === 1 ? " is-single" : ""}`}>
            {Array.from({ length: n }, (_, k) => <i key={k} />)}
          </span>
        ))}
      </div>
      <p className="xnote">{sizes.length} components · largest {int(sizes[0] ?? 0)} channels · {isolated} isolated</p>
    </div>
  );
}

function ModelCard({ r }: { r: Representation }) {
  const chips = Object.entries(r.config ?? {}).filter(([k]) => k !== "dimensions" && k !== "metapaths").slice(0, 6);
  const metapaths = typeof r.config?.metapaths === "string" ? r.config.metapaths.split(",").map((m) => m.trim()) : [];
  return (
    <article className="model">
      <header className="model__head">
        <span className="model__icon" aria-hidden="true">{r.method.slice(0, 1).toUpperCase()}</span>
        <div><strong>{r.method}</strong><small>{r.role ?? (r.status === "missing" ? "no stored run" : "")}</small></div>
        {r.status === "missing" ? <Badge tone="neutral">Not run</Badge> : <Badge tone={r.validation_passed ? "ok" : "warn"}>{r.validation_passed ? "Validated" : "Not validated"}</Badge>}
      </header>
      {r.status === "available" ? (
        <>
          <div className="model__nums">
            <div><b>{int(r.dimensions)}</b><span>dimensions</span></div>
            <div><b>{pct(r.coverage_ratio, 0)}</b><span>channel coverage</span></div>
          </div>
          <div className="meter" aria-hidden="true"><i style={{ width: `${(r.coverage_ratio ?? 0) * 100}%` }} /></div>
          {metapaths.length > 0 && <ul className="model__paths" aria-label="Metapaths">{metapaths.map((m) => <li key={m}>{m}</li>)}</ul>}
          <ul className="model__chips">{chips.map(([k, v]) => <li key={k}><span>{label(k)}</span><b>{scalar(v)}</b></li>)}</ul>
          <p className="model__run"><code>{r.experiment_id}</code></p>
        </>
      ) : <p className="muted small">No stored run for this snapshot.</p>}
    </article>
  );
}

function Diffusion({ x }: { x: DiffusionSummary }) {
  if (x.status === "missing") return <EmptyState title="Not run"><p>No diffusion run is stored for this snapshot.</p></EmptyState>;
  const used = x.iterations_max && x.max_iterations ? x.iterations_max / x.max_iterations : null;
  return (
    <div className="diff">
      <Gauge value={x.sources ? (x.converged_sources ?? 0) / x.sources : null} label="Sources converged" caption={`${int(x.converged_sources)} / ${int(x.sources)} sources converged`} />
      <div className="diff__iter">
        <span>Iterations used (slowest source)</span>
        <div className="meter" aria-hidden="true"><i style={{ width: `${Math.max(2, (used ?? 0) * 100)}%` }} /></div>
        <small>{int(x.iterations_max)} of {int(x.max_iterations)} allowed</small>
      </div>
      <ul className="model__chips">
        <li><span>Alpha (damping)</span><b>{scalar(x.alpha)}</b></li>
        <li><span>Tolerance</span><b>{x.tolerance === null || x.tolerance === undefined ? "—" : x.tolerance.toExponential(0)}</b></li>
        <li><span>Largest residual</span><b>{x.residual_max === null || x.residual_max === undefined ? "—" : x.residual_max.toExponential(2)}</b></li>
        <li><span>Topic edges</span><b>{x.include_topic_edges ? "included" : "excluded"}</b></li>
        <li><span>Diffusion graph</span><b>{compactN(x.graph_nodes)} nodes · {compactN(x.graph_edges)} edges</b></li>
        <li><span>Directionality</span><b>{label(String(x.directionality ?? "—"))}</b></li>
      </ul>
      <p className="model__run"><code>{x.experiment_id}</code></p>
    </div>
  );
}

/** Layout of the graph map: lane 1 holds the node types (the schema), lane 2 the views and models built on it. */
const W = 1040, H = 590;
const LANES: FlowLane[] = [
  { id: "structure", title: "Graph structure · node types and stored relations", x: 12, y: 10, w: W - 24, h: 360 },
  { id: "models", title: "Built on the graph · overlap, embeddings, diffusion", x: 12, y: 388, w: W - 24, h: 190 },
];
const POS: Record<string, { x: number; y: number; w: number; h: number }> = {
  commenter: { x: 40, y: 150, w: 240, h: 96 }, video: { x: 400, y: 44, w: 240, h: 96 },
  channel: { x: 760, y: 150, w: 240, h: 96 }, topic: { x: 400, y: 262, w: 240, h: 96 },
  overlap: { x: 26, y: 440, w: 242, h: 112 }, m2v: { x: 278, y: 440, w: 242, h: 112 },
  hgt: { x: 530, y: 440, w: 242, h: 112 }, ppr: { x: 782, y: 440, w: 242, h: 112 },
};
const TYPE_TEXT: Record<string, string> = { commenter: "Public commenters (pseudonymised)", video: "Collected public videos", channel: "Research channels", topic: "Content topics" };
type Tone = "ok" | "stored" | "missing" | "neutral";

const ICONS: Record<string, [string, string]> = {
  commenter: ["users", "#8b5cf6"], video: ["play", "#ef4444"], channel: ["broadcast", "#2563eb"], topic: ["tag", "#f59e0b"],
  overlap: ["venn", "#14b8a6"], m2v: ["route", "#6366f1"], hgt: ["neural", "#a855f7"], ppr: ["ripple", "#0ea5e9"],
};

function cardHead(id: string, title: string, value: string) {
  const [icon, color] = ICONS[id] ?? ["graph", "#2563eb"];
  return (
    <span className="schema-card__head">
      <span className="gicon" style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, boxShadow: `0 3px 8px ${color}55` }}><Icon name={icon} size={16} /></span>
      <strong>{title}</strong><b>{value}</b>
    </span>
  );
}

function StatusDot({ tone }: { tone: Tone }) {
  const text = tone === "ok" ? "validated" : tone === "stored" ? "stored" : tone === "missing" ? "not run" : "derived";
  return <span className={`gstatus gstatus--${tone}`}>{text}</span>;
}

function GraphMap({ d, selected, onSelect }: { d: GraphSummaryResponse; selected: string; onSelect: (id: string) => void }) {
  const deg = new Map(d.degree_distribution.map((x) => [x.node_type, x]));
  const rep = (m: string) => d.representations.find((r) => r.method.toLowerCase() === m);
  const repTone = (r?: Representation): Tone => (!r || r.status === "missing" ? "missing" : r.validation_passed ? "ok" : "stored");
  const nodes: FlowNode[] = [];
  for (const t of ["commenter", "video", "channel", "topic"]) {
    if (!(t in d.node_counts)) continue;
    nodes.push({ id: t, ...POS[t], tone: "stored", selected: selected === t, label: `${label(t)}: ${int(d.node_counts[t])} nodes`,
      content: (
        <span className="schema-card">
          {cardHead(t, label(t), int(d.node_counts[t]))}
          <span className="schema-card__text">{TYPE_TEXT[t]}</span>
          <span className="schema-card__meta">degree · mean {num(deg.get(t)?.mean_degree ?? null, 1)} · max {int(deg.get(t)?.max_degree ?? null)}</span>
        </span>
      ) });
  }
  const linked = d.channel_connectivity.filter((c) => c.connected_channels > 0).length;
  nodes.push({ id: "overlap", ...POS.overlap, tone: "neutral", selected: selected === "overlap", label: "Channel overlap: shared commenters between channels",
    content: (
      <span className="schema-card">
        {cardHead("overlap", "Channel overlap", `${linked}/${d.channel_connectivity.length}`)}
        <span className="schema-card__text">{int(d.channel_pairs_with_shared_commenters)} linked pairs · {int(d.commenters_on_multiple_channels)} shared</span>
        <span className="schema-card__foot"><StatusDot tone="neutral" /><span>{d.connected_components.filter((c) => c === 1).length} isolated channels</span></span>
      </span>
    ) });
  for (const [id, m] of [["m2v", "metapath2vec"], ["hgt", "hgt"]] as const) {
    const r = rep(m);
    nodes.push({ id, ...POS[id], tone: repTone(r), selected: selected === id, label: `${r?.method ?? m}: ${r?.status === "available" ? "stored" : "Not run"}`,
      content: (
        <span className="schema-card">
          {cardHead(id, r?.method ?? m, r?.dimensions ? `${r.dimensions}-dim` : "")}
          <span className="schema-card__text">{id === "m2v" ? "Metapath walks + skip-gram" : "Graph transformer"} · {r?.role?.split(" ")[0] ?? "embedding"}</span>
          <span className="schema-card__foot"><StatusDot tone={repTone(r)} />{r?.status === "available" && <span>coverage {pct(r.coverage_ratio, 0)}</span>}</span>
        </span>
      ) });
  }
  const x = d.diffusion;
  const pprTone: Tone = x.status === "missing" ? "missing" : x.validation_passed ? "ok" : "stored";
  nodes.push({ id: "ppr", ...POS.ppr, tone: pprTone, selected: selected === "ppr",
    label: `Personalized PageRank: ${x.status === "missing" ? "Not run" : `${x.converged_sources} of ${x.sources} sources converged`}`,
    content: (
      <span className="schema-card">
        {cardHead("ppr", "PageRank", x.status === "missing" ? "" : `${int(x.converged_sources)}/${int(x.sources)}`)}
        <span className="schema-card__text">From every channel · α {scalar(x.alpha)}</span>
        <span className="schema-card__foot"><StatusDot tone={pprTone} />{x.status !== "missing" && <span>{int(x.iterations_max)} iterations</span>}</span>
      </span>
    ) });

  const edges: FlowEdge[] = d.relations.flatMap((r) => (r.source_type && r.target_type && POS[r.source_type] && POS[r.target_type] ? [r] : [])).map((r) => ({
    from: r.source_type as string, to: r.target_type as string, dir: r.target_type === "topic" ? "down" : "right", dashed: r.derived,
    color: r.derived ? "#94a3b8" : "#2563eb", width: r.derived ? 1.5 : 2.5, label: `${r.relation} · ${int(r.edges)}`,
    labelAt: r.derived ? 0.16 : r.target_type === "topic" ? 0.78 : 0.5,
  }));
  if ("commenter" in d.node_counts) edges.push({ from: "commenter", to: "overlap", dashed: true, color: "#94a3b8", label: "derived", labelAt: 0.55 });
  if ("channel" in d.node_counts) edges.push({ from: "channel", to: "ppr", color: "#2563eb", width: 2, label: `${int(x.sources ?? channels(d))} seeds`, labelAt: 0.55 });

  return (
    <>
      <FlowLegend items={[
        { kind: "dot", tone: "ok", label: "Stored · validated" }, { kind: "dot", tone: "stored", label: "Stored" }, { kind: "dot", tone: "missing", label: "Not run" },
        { kind: "line", label: "Relation / feeds into" }, { kind: "dash", label: "Derived (summary)" },
      ]} />
      <FlowCanvas width={W} height={H} lanes={LANES} nodes={nodes} edges={edges} onSelect={onSelect} label="Research graph map" minScale={0.55} />
      <p className="xnote">metapath2vec and HGT are trained on the whole heterogeneous graph; their channel embeddings feed the score's embedding component.</p>
    </>
  );
}

const channels = (d: GraphSummaryResponse) => d.node_counts.channel ?? d.channel_connectivity.length;

function Connectivity({ d }: { d: GraphSummaryResponse }) {
  const maxConn = Math.max(1, ...d.channel_connectivity.map((c) => c.connected_channels));
  if (d.channel_connectivity.length === 0) return <EmptyState title="No channel overlap available" />;
  return (
    <ol className="conn-list conn-list--narrow" aria-label="Channel connectivity">
      {d.channel_connectivity.map((c) => (
        <li key={c.channel_id}>
          <Link to={`/channels?channel=${encodeURIComponent(c.channel_id)}`}><ChannelAvatar id={c.channel_id} name={c.channel_name} size={20} />{c.channel_name ?? c.channel_id}</Link>
          <span className="conn-list__track" aria-hidden="true"><i style={{ width: `${(c.connected_channels / maxConn) * 100}%` }} /></span>
          <span className="conn-list__value">{c.connected_channels === 0 ? <span className="muted">isolated</span> : `${int(c.connected_channels)} ch`}</span>
        </li>
      ))}
    </ol>
  );
}

/** Drawer content for the selected card. */
function Details({ id, d }: { id: string; d: GraphSummaryResponse }) {
  if (id in TYPE_TEXT) {
    const x = d.degree_distribution.find((v) => v.node_type === id);
    const rels = d.relations.filter((r) => r.source_type === id || r.target_type === id);
    return (
      <>
        <ul className="model__chips">
          <li><span>Nodes</span><b>{int(d.node_counts[id])}</b></li>
          <li><span>Mean / max degree</span><b>{num(x?.mean_degree ?? null, 2)} / {int(x?.max_degree ?? null)}</b></li>
        </ul>
        <h4 className="gx__sub">Relations</h4>
        <ul className="rel-tags">
          {rels.map((r) => <li key={r.relation} className={r.derived ? "is-derived" : ""}><code>{r.relation}</code><span>{r.source_type} → {r.target_type}</span><b>{int(r.edges)}</b></li>)}
        </ul>
        {x && (
          <>
            <h4 className="gx__sub">Degree distribution</h4>
            <Histogram bins={x.bins} label={`${label(id)} degree distribution`} />
          </>
        )}
        {id === "channel" && <><h4 className="gx__sub">Channels sharing commenters</h4><Connectivity d={d} /></>}
      </>
    );
  }
  if (id === "overlap") {
    const n = channels(d), possible = n > 1 ? (n * (n - 1)) / 2 : null, commenters = d.node_counts.commenter ?? null;
    return (
      <>
        <div className="gauges">
          <Gauge value={commenters && d.commenters_on_multiple_channels !== null ? d.commenters_on_multiple_channels / commenters : null}
            label="Commenters on 2+ channels" caption={`${int(d.commenters_on_multiple_channels)} of ${int(commenters)}`} />
          <Gauge value={possible && d.channel_pairs_with_shared_commenters !== null ? d.channel_pairs_with_shared_commenters / possible : null}
            label="Channel pairs linked" caption={`${int(d.channel_pairs_with_shared_commenters)} of ${int(possible)} pairs`} />
        </div>
        <h4 className="gx__sub">Connected components</h4>
        <Components sizes={d.connected_components} />
        <h4 className="gx__sub">Channel connectivity</h4>
        <Connectivity d={d} />
      </>
    );
  }
  if (id === "m2v" || id === "hgt") {
    const r = d.representations.find((x) => x.method.toLowerCase() === (id === "m2v" ? "metapath2vec" : "hgt"));
    return r ? <><ModelCard r={r} /><p className="small"><Link to="/neural">Open Neural Models →</Link></p></> : <EmptyState title="Not run" />;
  }
  if (id === "ppr") return <Diffusion x={d.diffusion} />;
  return null;
}

const TITLES: Record<string, string> = { overlap: "Channel overlap", m2v: "metapath2vec", hgt: "HGT", ppr: "Personalized PageRank" };

export function GraphPage() {
  const { snapshotId } = useResearch();
  const [params, setParams] = useSearchParams();
  const selected = params.get("node") ?? "";
  const g = useApi((s) => component3Api.graphSummary({ snapshotId }, s), [snapshotId]);

  return (
    <>
      {g.status === "loading" && <Loading variant="graph" label="Loading graph summary…" />}
      {g.status === "error" && <ErrorState error={g.error} onRetry={g.reload} what="Graph summary" />}
      {g.status === "success" && (() => {
        const d = g.data;
        const types = [...Object.keys(d.node_counts)].sort((a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b));
        const total = types.reduce((a, t) => a + d.node_counts[t], 0) || 1;
        const title = TITLES[selected] ?? (selected in TYPE_TEXT ? `${label(selected)} nodes` : "");
        return (
          <div className="gx">
            <section className="xhero gx__hero" aria-label="Graph summary">
              <span className="gx__mark" aria-hidden="true"><Icon name="graph" size={32} /></span>
              <div className="xhero__id">
                <h1>Heterogeneous research graph</h1>
                <p>Channels, videos, public commenters and topics · built {date(d.built_at)} · snapshot <code>{d.snapshot_id}</code></p>
                <div className="stackbar stackbar--lg" aria-hidden="true">
                  {types.map((t) => <i key={t} style={{ width: `${(d.node_counts[t] / total) * 100}%`, background: NODE_COLORS[t] ?? "#cbd5e1" }} />)}
                </div>
                <ul className="gx__legend">
                  {types.map((t) => (
                    <li key={t}><i style={{ background: NODE_COLORS[t] ?? "#cbd5e1" }} /><span>{label(t)}</span><b>{int(d.node_counts[t])}</b></li>
                  ))}
                </ul>
              </div>
              <div className="xhero__facts">
                <div><strong>{compactN(d.total_nodes)}</strong><span>nodes</span></div>
                <div><strong>{compactN(d.total_edges)}</strong><span>edges · {compactN(d.total_edges_excluding_derived)} observed</span></div>
                <div><strong>{d.relations.length}</strong><span>relations</span></div>
              </div>
            </section>

            <section className="xblock" aria-label="Graph map">
              <header className="xblock__head"><div><h3>Graph map</h3><p>The graph and the models built on it.</p></div></header>
              <GraphMap d={d} selected={selected} onSelect={(id) => setParams(id === selected ? {} : { node: id })} />
            </section>

            {selected && title && (
              <section className="xblock step-panel" aria-label={title}>
                <header className="xblock__head">
                  <div><h3>{title}</h3></div>
                  <button type="button" className="link-button" onClick={() => setParams({})}>Close</button>
                </header>
                <Details id={selected} d={d} />
              </section>
            )}
            <Provenance snapshotId={d.snapshot_id} />
          </div>
        );
      })()}
    </>
  );
}
