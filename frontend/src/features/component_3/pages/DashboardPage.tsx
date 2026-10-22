import { useContext, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChannelAvatar, ChannelIconContext, colorFor, initials } from "../../../components/common/ChannelAvatar";
import { Icon } from "../../../components/common/Icon";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num, pct } from "../../../utils/format";
import { TableWrap } from "../../../components/common/ui";
import { component3Api } from "../api";
import { liveApi } from "../liveApi";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { BridgePairRow, GraphSummaryResponse, ResearchStatusResponse } from "../types";

type Readiness = "Ready" | "Incomplete" | "Unavailable" | "Unknown";

/** Research status per pipeline area, derived only from what the API reports. The API reports stored
 * artifacts, not running jobs, so "Running" is never inferred. */
function researchStatus(status: ResearchStatusResponse | null, graph: GraphSummaryResponse | null) {
  const has = (name: string) => status?.artifacts.find((a) => a.name === name)?.status === "available";
  const all = (flags: boolean[]): Readiness => (flags.every(Boolean) ? "Ready" : flags.some(Boolean) ? "Incomplete" : "Unavailable");
  const reps = graph?.representations ?? [];
  const known = (r: Readiness): Readiness => (status ? r : "Unknown");
  return [
    { area: "Data", detail: "research snapshot", state: known(status?.research_data === "available" ? "Ready" : "Unavailable"), to: "/experiments" },
    { area: "Graph", detail: "heterogeneous graph + features", state: known(all([has("heterogeneous_graph"), has("graph_features")])), to: "/graph" },
    { area: "Representation learning", detail: "metapath2vec · HGT", state: graph ? all(reps.map((r) => r.status === "available")) : "Unknown" as Readiness, to: "/neural" },
    { area: "Diffusion", detail: "Personalized PageRank", state: known(all([has("ppr_diffusion")])), to: "/graph" },
    { area: "Topic modeling", detail: "semantic topic similarity", state: known(all([has("topic_similarity")])), to: "/topics" },
    { area: "Scoring", detail: "Audience Bridge Score", state: known(all([has("audience_bridge_scores")])), to: "/bridges" },
    { area: "Evaluation", detail: "baselines + evaluation", state: known(all([has("evaluations"), has("baseline_louvain"), has("baseline_node2vec")])), to: "/evaluation" },
  ];
}

/** The research models of the method, each with whether a stored run exists. */
function models(status: ResearchStatusResponse | null, graph: GraphSummaryResponse | null) {
  const has = (name: string) => status?.artifacts.find((a) => a.name === name)?.status === "available";
  const rep = (m: string) => graph?.representations.find((r) => r.method.toLowerCase() === m)?.status === "available";
  return [
    { name: "metapath2vec", kind: "graph embedding", ok: rep("metapath2vec"), to: "/neural" },
    { name: "HGT", kind: "graph neural network", ok: rep("hgt"), to: "/neural" },
    { name: "Personalized PageRank", kind: "diffusion", ok: has("ppr_diffusion"), to: "/graph" },
    { name: "Topic similarity", kind: "semantic", ok: has("topic_similarity"), to: "/topics" },
    { name: "Audience Bridge Score", kind: "proposed", ok: has("audience_bridge_scores"), to: "/bridges" },
    { name: "Louvain", kind: "baseline", ok: has("baseline_louvain"), to: "/evaluation" },
    { name: "node2vec", kind: "baseline", ok: has("baseline_node2vec"), to: "/evaluation" },
  ];
}

/** Circular gauge for a stored 0–1 score. */
function ScoreRing({ value, size = 124 }: { value: number | null; size?: number }) {
  const r = size / 2 - 9, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value ?? 0));
  return (
    <svg className="ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Audience Bridge Score ${num(value, 3)} of 1`}>
      <defs><linearGradient id="gi-ring" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#2563eb" /><stop offset=".6" stopColor="#7c3aed" /><stop offset="1" stopColor="#db2777" /></linearGradient></defs>
      <circle cx={size / 2} cy={size / 2} r={r} className="ring__track" />
      <circle cx={size / 2} cy={size / 2} r={r} className="ring__value" strokeDasharray={`${c * v} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="48%" textAnchor="middle" className="ring__num">{num(value, 3)}</text>
      <text x="50%" y="64%" textAnchor="middle" className="ring__cap">score</text>
    </svg>
  );
}

/** Number of stored scores per 0.1-wide bin (a count, nothing estimated). */
function ScoreHistogram({ rows }: { rows: BridgePairRow[] }) {
  const bins = Array.from({ length: 10 }, () => 0);
  for (const r of rows) if (r.audience_bridge_score !== null) bins[Math.min(9, Math.floor(r.audience_bridge_score * 10))] += 1;
  const max = Math.max(1, ...bins);
  return (
    <div className="mini-hist" role="img" aria-label={`Stored scores per 0.1 bin: ${bins.join(", ")}`}>
      {bins.map((b, i) => <span key={i} style={{ height: `${Math.max(4, Math.sqrt(b / max) * 100)}%` }} className={b === 0 ? "is-empty" : ""} title={`${(i / 10).toFixed(1)}–${((i + 1) / 10).toFixed(1)}: ${b}`} />)}
    </div>
  );
}

const compact = (n: number) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);

/** Small vertical bars (real values), lightest first. */
function MiniBars({ values, label: aria }: { values: number[]; label: string }) {
  const max = Math.max(1, ...values);
  return (
    <div className="gi-bars" role="img" aria-label={aria}>
      {values.map((v, i) => <i key={i} style={{ height: `${Math.max(8, Math.sqrt(v / max) * 100)}%`, opacity: 0.35 + (0.65 * (i + 1)) / values.length }} />)}
    </div>
  );
}

/** Small area line (real values, square-root scaled so small values stay visible). */
function MiniArea({ values, label: aria, id }: { values: number[]; label: string; id: string }) {
  if (values.length < 2) return <div className="gi-area" />;
  const W = 160, H = 64, max = Math.max(1, ...values);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * W, H - 4 - Math.sqrt(v / max) * (H - 10)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg className="gi-area" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={aria}>
      <defs><linearGradient id={`gia-${id}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--c)" stopOpacity=".3" /><stop offset="1" stopColor="var(--c)" stopOpacity="0" /></linearGradient></defs>
      <path d={`${line} L${W},${H} L0,${H} Z`} fill={`url(#gia-${id})`} />
      <path d={line} fill="none" stroke="var(--c)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

const TREND_COLORS = ["#2563eb", "#db2777", "#7c3aed", "#0891b2"];

/** Bridge-score trend of the four strongest live pairs over the nightly runs (research.c3_live_*). */
function LiveTrend() {
  const live = useApi((sg) => liveApi.bridges(500, sg), []);
  const top = live.status === "success" ? live.data.items.filter((b) => (b.audience_bridge_score ?? 0) > 0).slice(0, 4) : [];
  const key = top.map((b) => `${b.source_channel_id}>${b.destination_channel_id}`).join("|");
  const hist = useApi((sg) => Promise.all(top.map((b) => liveApi.history(b.source_channel_id, b.destination_channel_id, sg))), [key], top.length > 0);
  const runs = hist.status === "success" ? [...new Set(hist.data.flatMap((h) => h.items.map((p) => p.finished_at)))].sort() : [];
  const W = 520, H = 210, L = 34, R = 34, T = 12, B = 28;
  const x = (t: string) => L + (runs.length > 1 ? (runs.indexOf(t) / (runs.length - 1)) * (W - L - R) : (W - L - R) / 2);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  return (
    <section className="panel gi-panel" aria-label="Live bridge trend">
      <header className="panel__head">
        <div><h2><Icon name="status" size={17} /> Audience bridge trend</h2><p>Strongest live pairs across the nightly runs{live.status === "success" && live.data.offline ? " · offline copy" : ""}.</p></div>
        <Link to="/live">Live results <Icon name="arrow" size={14} /></Link>
      </header>
      {live.status === "loading" || hist.status === "loading" ? <Loading variant="chart" label="Loading live trend…" /> :
        live.status === "error" ? <p className="muted gi-note">{live.error.code === "storage_unavailable" ? "The shared database is not reachable from this network. Switch network to load the live trend." : "Live results are not available yet."}</p> :
        top.length === 0 ? <p className="muted gi-note">No live bridge evidence yet.</p> : hist.status === "success" && (
          <>
            <svg className="gi-trend" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Bridge score of ${top.length} live pairs over ${runs.length} nightly runs`}>
              {[0, 0.25, 0.5, 0.75, 1].map((v) => (
                <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="gi-trend__grid" /><text x={L - 6} y={y(v) + 3} textAnchor="end" className="gi-trend__ax">{v.toFixed(2)}</text></g>
              ))}
              {runs.map((t) => <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="gi-trend__ax">{date(t).slice(5, 16)}</text>)}
              {hist.data.map((h, k) => {
                const pts = h.items.filter((p) => p.audience_bridge_score !== null);
                const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p.finished_at)},${y(p.audience_bridge_score as number)}`).join(" ");
                return (
                  <g key={k}>
                    {pts.length > 1 && <path d={d} fill="none" stroke={TREND_COLORS[k]} strokeWidth="2.2" />}
                    {pts.map((p) => <circle key={p.run_id} cx={x(p.finished_at)} cy={y(p.audience_bridge_score as number)} r="3.5" fill="#fff" stroke={TREND_COLORS[k]} strokeWidth="2" />)}
                  </g>
                );
              })}
            </svg>
            <ul className="gi-legend">
              {top.map((b, k) => <li key={k}><i style={{ background: TREND_COLORS[k] }} />{b.source_channel_name} → {b.destination_channel_name}</li>)}
            </ul>
          </>
        )}
    </section>
  );
}

/** Directed network of the strongest stored bridges between channel icons (arrow = source → destination). */
function BridgeNet({ rows, order, onOpen, size }: { rows: BridgePairRow[]; order: string[]; onOpen: (s: string, d: string) => void; size: Map<string, number> }) {
  const icons = useContext(ChannelIconContext);
  const W = 1100, H = 520, CX = W / 2, CY = H / 2, R = 210, RX = 400;
  const maxSize = Math.max(1, ...size.values());
  const rad = (id: string) => 15 + 11 * Math.sqrt((size.get(id) ?? 0) / maxSize);
  const ids = [...new Set(rows.flatMap((r) => [r.source_channel_id, r.destination_channel_id]))];
  const names = new Map(rows.flatMap((r) => [[r.source_channel_id, r.source_channel_name], [r.destination_channel_id, r.destination_channel_name]] as [string, string | null][]));
  const pos = new Map(ids.map((id, i) => {
    const a = (-90 + (360 * i) / ids.length) * (Math.PI / 180);
    return [id, { x: CX + RX * Math.cos(a), y: CY + R * Math.sin(a), a }];
  }));
  const vs = rows.map((r) => r.audience_bridge_score ?? 0), lo = Math.min(...vs), hi = Math.max(...vs);
  const t = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 1);
  return (
    <svg className="bnet2" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Strongest bridges: ${rows.map((r) => `${r.source_channel_name} to ${r.destination_channel_name} ${num(r.audience_bridge_score, 3)}`).join("; ")}`}>
      <defs>
        <marker id="bn2-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,1 L10,5 L0,9 z" fill="#4f46e5" /></marker>
        <radialGradient id="bn2-bg"><stop offset="0%" stopColor="#eef2ff" /><stop offset="100%" stopColor="#fff" stopOpacity="0" /></radialGradient>
        {ids.map((id) => <clipPath key={id} id={`bn2-c-${id}`}><circle cx={pos.get(id)!.x} cy={pos.get(id)!.y} r={rad(id)} /></clipPath>)}
      </defs>
      <ellipse cx={CX} cy={CY} rx={RX + 40} ry={R + 36} fill="url(#bn2-bg)" />
      {rows.map((r) => {
        const a = pos.get(r.source_channel_id)!, b = pos.get(r.destination_channel_id)!;
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
        const ra = rad(r.source_channel_id) + 6, rb = rad(r.destination_channel_id) + 8;
        const sx = a.x + (dx / d) * ra, sy = a.y + (dy / d) * ra, ex = b.x - (dx / d) * rb, ey = b.y - (dy / d) * rb;
        const mx = (sx + ex) / 2 - (dy / d) * 22, my = (sy + ey) / 2 + (dx / d) * 22;
        const v = r.audience_bridge_score ?? 0;
        const lx = 0.25 * sx + 0.5 * mx + 0.25 * ex, ly = 0.25 * sy + 0.5 * my + 0.25 * ey;
        return (
          <g key={`${r.source_channel_id}>${r.destination_channel_id}`} className="bnet2__edge" onClick={() => onOpen(r.source_channel_id, r.destination_channel_id)}>
            <title>{`${r.source_channel_name} → ${r.destination_channel_name}: ${num(v, 3)}`}</title>
            <path d={`M${sx},${sy} Q${mx},${my} ${ex},${ey}`} fill="none" stroke="#6366f1" strokeOpacity={0.35 + 0.6 * t(v)} strokeWidth={1.5 + 4 * t(v)} markerEnd="url(#bn2-arrow)" />
            <rect x={lx - 19} y={ly - 9} width={38} height={18} rx={9} className="bnet2__pill" />
            <text x={lx} y={ly + 4} textAnchor="middle" className="bnet2__val">{v.toFixed(2)}</text>
          </g>
        );
      })}
      {ids.map((id) => {
        const p = pos.get(id)!, src = icons.get(id), name = names.get(id) ?? id, right = Math.cos(p.a) >= -0.01;
        return (
          <g key={id}>
            <circle cx={p.x} cy={p.y} r={rad(id) + 4} className="bnet2__halo" />
            {src ? <image href={src} x={p.x - rad(id)} y={p.y - rad(id)} width={2 * rad(id)} height={2 * rad(id)} clipPath={`url(#bn2-c-${id})`} preserveAspectRatio="xMidYMid slice" />
              : <><circle cx={p.x} cy={p.y} r={rad(id)} fill={colorFor(id, order)} /><text x={p.x} y={p.y + 4} textAnchor="middle" className="tnet__init">{initials(name)}</text></>}
            <text x={p.x + (Math.abs(Math.cos(p.a)) < 0.2 ? 0 : right ? rad(id) + 10 : -rad(id) - 10)} y={p.y + (Math.abs(Math.cos(p.a)) < 0.2 ? (Math.sin(p.a) < 0 ? -rad(id) - 10 : rad(id) + 18) : 4)}
              textAnchor={Math.abs(Math.cos(p.a)) < 0.2 ? "middle" : right ? "start" : "end"} className="bnet2__label">{name}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Distribution of all stored scores in 0.1 bins, with counts and axis labels. */
function ScoreDistribution({ rows }: { rows: BridgePairRow[] }) {
  const bins = Array.from({ length: 10 }, () => 0);
  for (const r of rows) if (r.audience_bridge_score !== null) bins[Math.min(9, Math.floor(r.audience_bridge_score * 10))] += 1;
  const max = Math.max(1, ...bins);
  const zero = rows.filter((r) => r.audience_bridge_score === 0).length;
  const scored = rows.filter((r) => r.audience_bridge_score !== null);
  const median = scored.length ? [...scored].map((r) => r.audience_bridge_score as number).sort((a, b) => a - b)[Math.floor(scored.length / 2)] : null;
  return (
    <div className="sdist">
      <div className="sdist__bars" role="img" aria-label={`Bridge scores per 0.1 bin: ${bins.map((b, i) => `${(i / 10).toFixed(1)}: ${b}`).join(", ")}`}>
        {bins.map((b, i) => (
          <div key={i} className="sdist__col">
            <span className="sdist__n">{b || ""}</span>
            <span className="sdist__bar" style={{ height: `${Math.max(2, Math.sqrt(b / max) * 100)}%`, background: `color-mix(in srgb, #2563eb ${30 + i * 7}%, #a5b4fc)` }} />
            <span className="sdist__x">{(i / 10).toFixed(1)}</span>
          </div>
        ))}
      </div>
      <ul className="sdist__facts">
        <li><b>{int(zero)}</b><span>pairs at 0 (no shared commenters)</span></li>
        <li><b>{int(scored.length - zero)}</b><span>pairs with a positive score</span></li>
        <li><b>{num(median, 3)}</b><span>median score</span></li>
      </ul>
    </div>
  );
}

const STEP_ICON: Record<string, string> = { Data: "overview", Graph: "graph", "Representation learning": "neural", Diffusion: "ripple", "Topic modeling": "tag", Scoring: "bridges", Evaluation: "evaluation" };

export function DashboardPage() {
  const { snapshotId, experimentId, status } = useResearch();
  const c = { snapshotId, experimentId };
  const navigate = useNavigate();
  const summary = useApi((s) => component3Api.dashboardSummary(c, s), [snapshotId]);
  const graph = useApi((s) => component3Api.graphSummary(c, s), [snapshotId]);
  const pairs = useApi((s) => component3Api.bridgePairs(c, s), [snapshotId, experimentId]);
  const perf = useApi((s) => component3Api.dashboardChannels(c, s), [snapshotId]);
  const items = useMemo(() => (pairs.status === "success" ? pairs.data.items : []), [pairs]);

  if (status.status === "success" && status.data.research_data === "missing") {
    return <EmptyState title="No research data available for this snapshot."><p>Run the collection pipeline and create a research snapshot first.</p></EmptyState>;
  }
  const s = summary.status === "success" ? summary.data : null;
  const g = graph.status === "success" ? graph.data : null;
  const st = status.status === "success" ? status.data : null;
  const scored = items.filter((r) => r.audience_bridge_score !== null);
  const positive = scored.filter((r) => (r.audience_bridge_score ?? 0) > 0);
  const top = scored[0];
  const byAudience = perf.status === "success" ? [...perf.data.items].sort((a, b) => (b.unique_commenters ?? 0) - (a.unique_commenters ?? 0)) : [];
  const order = byAudience.map((ch) => ch.channel_id);
  const maxAudience = Math.max(1, ...byAudience.map((ch) => ch.unique_commenters ?? 0));
  const multi = g?.commenters_on_multiple_channels != null && s?.unique_commenters ? g.commenters_on_multiple_channels / s.unique_commenters : null;
  const steps = researchStatus(st, g);
  const open = (src: string, dst: string) => navigate(`/bridges?source=${encodeURIComponent(src)}&destination=${encodeURIComponent(dst)}`);
  const pending = (failed: boolean) => (failed ? "n/a" : "…");
  const subs = new Map(byAudience.map((ch) => [ch.channel_id, ch.subscriber_count]));
  const byBridges = [...positive.reduce((m, r) => {
    const e = m.get(r.source_channel_id) ?? { id: r.source_channel_id, name: r.source_channel_name ?? r.source_channel_id, bridges: 0, conf: 0 };
    e.bridges += 1; e.conf += r.confidence_component ?? 0;
    return m.set(r.source_channel_id, e);
  }, new Map<string, { id: string; name: string; bridges: number; conf: number }>()).values()]
    .map((e) => ({ ...e, confidence: e.bridges ? e.conf / e.bridges : null, subscribers: subs.get(e.id) ?? null }))
    .sort((x, y) => y.bridges - x.bridges || (y.confidence ?? 0) - (x.confidence ?? 0));

  return (
    <div className="ov gi">
      <header className="gi-hero">
        <div className="gi-hero__text">
          <span className="gi-kicker">Research dashboard</span>
          <h1><span className="gi-grad">Cross-Channel</span><br /> Audience Bridge Analysis</h1>
          <p>Directional, confidence-weighted scoring of potential audience bridges between {s ? int(s.channels) : "the"} YouTube channels,
            built from public comment networks, graph diffusion and content similarity.</p>
          <nav className="gi-tiles" aria-label="Explore">
            <Link to="/graph" className="gi-tile" style={{ ["--c" as string]: "#2563eb" }}><span><Icon name="graph" size={17} /></span>Graph<br />analysis</Link>
            <Link to="/channels" className="gi-tile" style={{ ["--c" as string]: "#7c3aed" }}><span><Icon name="evaluation" size={17} /></span>Audience<br />insights</Link>
            <Link to="/bridges" className="gi-tile" style={{ ["--c" as string]: "#db2777" }}><span><Icon name="link" size={17} /></span>Cross-channel<br />connections</Link>
            <Link to="/topics" className="gi-tile" style={{ ["--c" as string]: "#0891b2" }}><span><Icon name="topic" size={17} /></span>Content<br />similarity</Link>
          </nav>
        </div>
        <div className="gi-orbit" aria-hidden="true">
          <span className="gi-orbit__ring gi-orbit__ring--1" />
          <span className="gi-orbit__ring gi-orbit__ring--2" />
          {["#3b82f6", "#ec4899", "#8b5cf6", "#06b6d4", "#3b82f6", "#ec4899"].map((col, k) => {
            const ang = (20 + k * 60) * (Math.PI / 180);
            return <i key={k} className="gi-orbit__dot" style={{ background: col, left: `${50 + 33 * Math.cos(ang)}%`, top: `${50 + 33 * Math.sin(ang)}%` }} />;
          })}
          <span className="gi-orbit__yt"><svg viewBox="0 0 68 48" width="58" height="41"><rect width="68" height="48" rx="12" fill="#ef4444" /><path d="M27 14v20l18-10z" fill="#fff" /></svg></span>
          {byAudience.slice(0, 5).map((ch, k) => {
            const ang = (-90 + k * 72) * (Math.PI / 180);
            return <span key={ch.channel_id} className="gi-orbit__ch" style={{ left: `${50 + 41 * Math.cos(ang)}%`, top: `${50 + 41 * Math.sin(ang)}%` }}><ChannelAvatar id={ch.channel_id} name={ch.channel_name} order={order} size={k === 0 ? 58 : 50} /></span>;
          })}
        </div>
      </header>

      {summary.status === "error" ? <ErrorState error={summary.error} onRetry={summary.reload} what="Snapshot totals" /> :
        summary.status === "loading" ? <Loading variant="cards" rows={4} label="Loading research metrics…" /> : (
          <section className="gi-kpis" aria-label="Research metrics">
            <article className="gi-kpi" style={{ ["--c" as string]: "#2563eb" }}>
              <header><span className="gi-kpi__ic"><Icon name="users" size={17} /></span>Channels analysed</header>
              <div className="gi-kpi__body">
                <div>
                  <strong className="gi-kpi__value">{s ? int(s.channels) : "—"}</strong>
                  <small className="gi-kpi__sub"><b>{s?.subscribers != null ? compact(s.subscribers) : "—"}</b> public subscribers</small>
                </div>
                <MiniBars values={byAudience.slice(0, 10).map((ch) => ch.unique_commenters ?? 0).reverse()} label="Unique commenters of the ten largest channels" />
              </div>
            </article>
            <article className="gi-kpi" style={{ ["--c" as string]: "#db2777" }}>
              <header><span className="gi-kpi__ic"><Icon name="comment" size={17} /></span>Public comments</header>
              <div className="gi-kpi__body">
                <div>
                  <strong className="gi-kpi__value">{s ? int(s.collected_comments) : "—"}</strong>
                  <small className="gi-kpi__sub"><b>{pct(multi, 1)}</b> cross-channel commenters</small>
                </div>
                <MiniArea values={byAudience.map((ch) => ch.collected_comments ?? 0).reverse()} label="Collected comments per channel" id="cm" />
              </div>
            </article>
            <article className="gi-kpi" style={{ ["--c" as string]: "#7c3aed" }}>
              <header><span className="gi-kpi__ic"><Icon name="graph" size={17} /></span>Graph nodes</header>
              <div className="gi-kpi__body">
                <div>
                  <strong className="gi-kpi__value">{g ? int(g.total_nodes) : pending(graph.status === "error")}</strong>
                  <small className="gi-kpi__sub"><b>{g ? int(g.total_edges) : "—"}</b> edges · {g ? Object.keys(g.node_counts).length : "—"} node types</small>
                </div>
                {g && (
                  <div className="gi-types" role="img" aria-label={Object.entries(g.node_counts).map(([t, n]) => `${t} ${n}`).join(", ")}>
                    {Object.entries(g.node_counts).map(([t, n]) => {
                      const mx = Math.max(1, ...Object.values(g.node_counts));
                      return <span key={t} title={`${label(t)}: ${int(n)}`}><i style={{ height: `${Math.max(8, Math.sqrt(n / mx) * 100)}%` }} /><small>{label(t).slice(0, 4)}</small></span>;
                    })}
                  </div>
                )}
              </div>
            </article>
            <article className="gi-kpi" style={{ ["--c" as string]: "#0891b2" }}>
              <header><span className="gi-kpi__ic"><Icon name="target" size={17} /></span>Scored directed pairs</header>
              <div className="gi-kpi__body">
                <div>
                  <strong className="gi-kpi__value">{pairs.status === "success" ? int(scored.length) : pending(pairs.status === "error")}</strong>
                  <small className="gi-kpi__sub"><b>{pairs.status === "success" && scored.length ? pct(positive.length / scored.length, 1) : "—"}</b> with shared-audience evidence</small>
                </div>
                {pairs.status === "success" && <ScoreHistogram rows={scored} />}
              </div>
            </article>
          </section>
        )}

      <div className="gi-row">
        <section className="panel gi-panel" aria-label="Top channels by potential bridges">
          <header className="panel__head">
            <div><h2><Icon name="evaluation" size={17} /> Top channels by potential bridges</h2></div>
            <Link to="/bridges">View all <Icon name="arrow" size={14} /></Link>
          </header>
          {pairs.status === "loading" && <Loading variant="table" rows={5} />}
          {pairs.status === "success" && (byBridges.length === 0 ? <EmptyState title="No bridge relationships are available for this snapshot." /> : (
            <TableWrap label="Channels ranked by number of potential bridges">
              <table className="gi-table">
                <thead><tr><th>#</th><th>Channel</th><th className="num">Subscribers</th><th className="num">Potential bridges</th><th>Avg. confidence</th></tr></thead>
                <tbody>
                  {byBridges.slice(0, 5).map((r, i) => (
                    <tr key={r.id}>
                      <td>{i + 1}</td>
                      <td><Link to={`/bridges?source=${encodeURIComponent(r.id)}`} className="gi-table__ch"><ChannelAvatar id={r.id} name={r.name} order={order} size={30} /> {r.name}</Link></td>
                      <td className="num">{r.subscribers != null ? int(r.subscribers) : "—"}</td>
                      <td className="num">{int(r.bridges)}</td>
                      <td><span className="gi-conf"><b>{num(r.confidence, 2)}</b><span><i style={{ width: `${(r.confidence ?? 0) * 100}%` }} /></span></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          ))}
        </section>
        <LiveTrend />
      </div>

      {pairs.status === "success" && positive.length > 0 && (
        <section className="panel" aria-label="Bridge network">
          <header className="panel__head">
            <div><h2><Icon name="graph" size={17} /> Bridge network</h2><p>The {Math.min(16, positive.length)} strongest directed bridges. Arrow = source → destination; thicker = stronger.</p></div>
            <Link to="/bridges">Full bridge graph <Icon name="arrow" size={14} /></Link>
          </header>
          <BridgeNet rows={positive.slice(0, 16)} order={order} onOpen={open} size={new Map(byAudience.map((c) => [c.channel_id, c.unique_commenters ?? 0]))} />
        </section>
      )}

      <div className="ov-hero">
        <section className="panel spotlight" aria-label="Strongest bridge">
          <header className="panel__head">
            <div><h2><Icon name="target" size={17} /> Strongest audience bridge</h2><p>Highest-scoring directed pair.</p></div>
          </header>
          {pairs.status === "loading" && <Loading variant="block" />}
          {pairs.status === "error" && <ErrorState error={pairs.error} onRetry={pairs.reload} what={`Bridge scores${experimentId ? ` for experiment ${experimentId}` : ""}`} />}
          {pairs.status === "success" && (!top ? <EmptyState title="No bridge relationships are available for this snapshot." /> : (
            <div className="spotlight__body">
              <div className="spotlight__pair">
                <div className="spotlight__ch">
                  <ChannelAvatar id={top.source_channel_id} name={top.source_channel_name} order={order} size={64} />
                  <span className="spotlight__role">Source</span>
                  <strong>{top.source_channel_name}</strong>
                </div>
                <div className="spotlight__arrow" aria-hidden="true"><span /><i /></div>
                <div className="spotlight__ch">
                  <ChannelAvatar id={top.destination_channel_id} name={top.destination_channel_name} order={order} size={64} />
                  <span className="spotlight__role">Destination</span>
                  <strong>{top.destination_channel_name}</strong>
                </div>
              </div>
              <ScoreRing value={top.audience_bridge_score} />
              <dl className="spotlight__facts">
                <div><dt>Confidence</dt><dd>{num(top.confidence_component, 3)}</dd></div>
                <div><dt>Shared commenters</dt><dd>{int(top.shared_commenters)}</dd></div>
                <div><dt>Topic similarity</dt><dd>{num(top.topic_similarity ?? null, 3)}</dd></div>
                <div className="spotlight__links">
                  <button type="button" className="button button--primary" onClick={() => open(top.source_channel_id, top.destination_channel_id)}>Open in bridge graph</button>
                  <Link to={`/explainability?source=${encodeURIComponent(top.source_channel_id)}&destination=${encodeURIComponent(top.destination_channel_id)}`}>Why this score?</Link>
                </div>
              </dl>
              <div className="spotlight__parts" aria-label="Score components of the strongest bridge">
                {([["Diffusion", top.diffusion_component, "#2563eb"], ["Embedding", top.embedding_component, "#6366f1"], ["Topic", top.topic_component, "#94a3b8"]] as [string, number | null, string][]).map(([k, v, col]) => (
                  <div key={k}>
                    <span>{k}</span>
                    <span className="spotlight__track"><i style={{ width: `${Math.max(0, Math.min(1, (v ?? 0) / Math.max(1e-9, top.base_score ?? 1))) * 100}%`, background: col }} /></span>
                    <b>{num(v, 3)}</b>
                  </div>
                ))}
                <p>Base score {num(top.base_score, 3)} × confidence {num(top.confidence_component, 3)} = {num(top.audience_bridge_score, 3)}. Bars show each component's share of the base score.</p>
              </div>
            </div>
          ))}
        </section>

        <section className="panel" aria-label="Ranked opportunities">
          <header className="panel__head">
            <div><h2><Icon name="bridges" size={17} /> Top bridges</h2><p>Highest-scoring directed pairs.</p></div>
            <Link to="/bridges">Open bridge graph <Icon name="arrow" size={14} /></Link>
          </header>
          {pairs.status === "loading" && <Loading variant="table" rows={6} />}
          {pairs.status === "success" && (scored.length === 0 ? <EmptyState title="No bridge relationships are available for this snapshot." /> : (
            <ul className="plist">
              {scored.slice(0, 7).map((r, i) => (
                <li key={`${r.source_channel_id}-${r.destination_channel_id}`}>
                  <button type="button" onClick={() => open(r.source_channel_id, r.destination_channel_id)}>
                    <span className={`ov-medal ov-medal--${i < 3 ? i + 1 : 0}`}>{i + 1}</span>
                    <span className="pairicons" aria-hidden="true">
                      <ChannelAvatar id={r.source_channel_id} name={r.source_channel_name} order={order} size={28} />
                      <ChannelAvatar id={r.destination_channel_id} name={r.destination_channel_name} order={order} size={28} />
                    </span>
                    <span className="plist__main">
                      <span className="plist__title">{r.source_channel_name} <span aria-label="to">→</span> {r.destination_channel_name}</span>
                      <span className="plist__bar" aria-hidden="true"><i style={{ width: `${(r.audience_bridge_score ?? 0) * 100}%` }} /></span>
                    </span>
                    <span className="score-pill">{num(r.audience_bridge_score, 3)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ))}
        </section>
      </div>

      <div className="ov-net">
        <section className="panel" aria-label="Channels by audience">
          <header className="panel__head">
            <div><h2><Icon name="users" size={17} /> Channels by audience</h2><p>Unique public commenters collected per channel.</p></div>
            <Link to="/channels">Channel explorer <Icon name="arrow" size={14} /></Link>
          </header>
          {perf.status === "loading" && <Loading variant="cards" rows={3} />}
          {perf.status === "error" && <ErrorState error={perf.error} onRetry={perf.reload} what="Channel totals" />}
          {perf.status === "success" && (
            <>
              <ol className="ov-podium">
                {[1, 0, 2].map((k) => byAudience[k]).filter(Boolean).map((ch) => {
                  const k = byAudience.indexOf(ch);
                  return (
                    <li key={ch.channel_id} className={`ov-podium__step ov-podium__step--${k + 1}`}>
                      <Link to={`/channels?channel=${encodeURIComponent(ch.channel_id)}`}>
                        <span className={`ov-medal ov-medal--${k + 1}`}>{k + 1}</span>
                        <ChannelAvatar id={ch.channel_id} name={ch.channel_name} order={order} size={k === 0 ? 56 : 46} />
                        <b>{ch.channel_name}</b>
                        <strong>{int(ch.unique_commenters)}</strong>
                        <small>commenters</small>
                      </Link>
                    </li>
                  );
                })}
              </ol>
              <ul className="plist">
                {byAudience.slice(3, 8).map((ch, k) => (
                  <li key={ch.channel_id}>
                    <Link to={`/channels?channel=${encodeURIComponent(ch.channel_id)}`} className="plist__row plist__row--link">
                      <span className="ov-medal ov-medal--0">{k + 4}</span>
                      <ChannelAvatar id={ch.channel_id} name={ch.channel_name} order={order} size={28} />
                      <span className="plist__main">
                        <span className="plist__title">{ch.channel_name}</span>
                        <span className="plist__bar plist__bar--soft" aria-hidden="true"><i style={{ width: `${((ch.unique_commenters ?? 0) / maxAudience) * 100}%` }} /></span>
                      </span>
                      <span className="plist__num"><strong>{int(ch.unique_commenters)}</strong><small>{int(ch.videos)} videos</small></span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
        {pairs.status === "success" && (
          <section className="panel" aria-label="Score distribution">
            <header className="panel__head"><div><h2><Icon name="evaluation" size={17} /> Score distribution</h2><p>All {int(scored.length)} scored directed pairs.</p></div></header>
            <ScoreDistribution rows={scored} />
          </section>
        )}
      </div>

      <section className="panel ov-pipe-panel">
        <header className="panel__head">
          <div><h2><Icon name="flow" size={17} /> Research pipeline</h2><p>Each stage of the method.</p></div>
          <Link to="/pipeline">Pipeline graph <Icon name="arrow" size={14} /></Link>
        </header>
        <section aria-label="Research status">
          {status.status === "loading" ? <Loading variant="table" rows={2} /> : status.status === "error" ? <ErrorState error={status.error} onRetry={status.reload} what="Research status" /> : (
            <ol className="ov-track">
              {steps.map((r, k) => (
                <li key={r.area} className={`is-${r.state.toLowerCase()}`}>
                  <span className="ov-track__node" aria-hidden="true"><Icon name={STEP_ICON[r.area] ?? "overview"} size={18} /><em>{k + 1}</em></span>
                  <Link to={r.to} className="ov-track__name">{r.area}</Link>
                  <small>{r.detail}</small>
                  <span className={`pill pill--${r.state.toLowerCase()}`}>{r.state}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
        <section className="ov-models" aria-label="Research models">
          <span className="ov-models__title">Models</span>
          <ul>
            {models(st, g).map((m) => (
              <li key={m.name}>
                <Link to={m.to} className={`chip${m.ok ? " is-ok" : ""}`}>
                  <i aria-hidden="true" /> <strong>{m.name}</strong> <span>{m.kind}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </section>

      <footer className="ws-foot">
        <p>{LIMITATIONS}</p>
        <Provenance snapshotId={s?.snapshot_id ?? null} experimentId={pairs.status === "success" ? pairs.data.experiment_id : null} />
      </footer>
    </div>
  );
}
