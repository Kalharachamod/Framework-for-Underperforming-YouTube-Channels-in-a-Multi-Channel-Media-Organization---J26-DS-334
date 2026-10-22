import { useContext, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Heatmap } from "../../../components/charts/Matrix";
import { ChannelAvatar, ChannelIconContext, colorFor, initials } from "../../../components/common/ChannelAvatar";
import { Icon } from "../../../components/common/Icon";
import { ErrorState, Loading } from "../../../components/common/States";
import { useApi } from "../../../hooks/useApi";
import { date, int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { TopicSummary } from "../types";

const TOPIC_COLORS = ["#1e3a8a", "#2563eb", "#3b82f6", "#0ea5e9", "#06b6d4", "#14b8a6", "#6366f1", "#8b5cf6", "#a855f7", "#64748b"];
const compactN = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);
type Ch = { id: string; label: string };

/** Panel with a title row; the visual inside carries the content. */
function Block({ title, hint, label: aria, action, children }: { title: string; hint?: string; label?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="xblock" aria-label={aria ?? title}>
      <header className="xblock__head"><div><h3>{title}</h3>{hint && <p>{hint}</p>}</div>{action}</header>
      {children}
    </section>
  );
}

/**
 * Sankey flow: channels (left) → the topic clusters their videos fall in (right). Band width = number of
 * collected videos (stored channel × topic counts). Hover highlights a channel's or topic's bands; click opens details.
 */
function TopicFlow({ items, flows, axis, selected, onSelect }: {
  items: TopicSummary[];
  flows: { channel_id: string; channel_name: string | null; topic_id: string; videos: number }[];
  axis: Ch[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const icons = useContext(ChannelIconContext);
  const [hover, setHover] = useState<string | null>(null);
  const W = 1000, TOP = 16, H = 640, GAP = 6, NW = 14, XL = 250, XR = W - 250;
  const total = flows.reduce((a, f) => a + f.videos, 0) || 1;
  const tIndex = new Map(items.map((t, i) => [t.topic_id, i]));
  // channels ordered by their main topic, then size, so bands cross as little as possible
  const chans = [...new Set(flows.map((f) => f.channel_id))].map((id) => {
    const fs = flows.filter((f) => f.channel_id === id);
    const main = [...fs].sort((a, b) => b.videos - a.videos)[0];
    return { id, name: fs[0].channel_name ?? axis.find((c) => c.id === id)?.label ?? id, videos: fs.reduce((a, f) => a + f.videos, 0), main: tIndex.get(main.topic_id) ?? 99 };
  }).sort((a, b) => a.main - b.main || b.videos - a.videos);
  const scale = (H - TOP * 2 - GAP * (Math.max(chans.length, items.length) - 1)) / total;
  const layout = <T extends { videos: number }>(list: T[]) => {
    const used = list.reduce((a, n) => a + n.videos * scale, 0) + GAP * (list.length - 1);
    let y = TOP + (H - TOP * 2 - used) / 2;
    return list.map((n) => { const r = { ...n, y, h: Math.max(2, n.videos * scale) }; y += r.h + GAP; return r; });
  };
  const L = layout(chans), R = layout(items.map((t, i) => ({ ...t, i })));
  const lPos = new Map(L.map((n) => [n.id, { ...n, cur: n.y }]));
  const rPos = new Map(R.map((n) => [n.topic_id, { ...n, cur: n.y }]));
  const ordered = [...flows].sort((a, b) => (L.findIndex((n) => n.id === a.channel_id) - L.findIndex((n) => n.id === b.channel_id)) || ((tIndex.get(a.topic_id) ?? 0) - (tIndex.get(b.topic_id) ?? 0)));
  const bands = ordered.map((f) => {
    const l = lPos.get(f.channel_id)!, r = rPos.get(f.topic_id)!;
    const h = f.videos * scale, y0 = l.cur, y1 = r.cur;
    l.cur += h; r.cur += h;
    const x0 = XL + NW, x1 = XR, mx = (x0 + x1) / 2;
    return { f, color: TOPIC_COLORS[(tIndex.get(f.topic_id) ?? 0) % TOPIC_COLORS.length],
      d: `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1} L${x1},${y1 + h} C${mx},${y1 + h} ${mx},${y0 + h} ${x0},${y0 + h} Z` };
  });
  const focus = hover ?? (selected || null);
  const active = (f: { channel_id: string; topic_id: string }) => !focus || focus === `c:${f.channel_id}` || focus === `t:${f.topic_id}`;
  const label = (n: string, max = 24) => (n.length > max ? `${n.slice(0, max - 1)}…` : n);

  return (
    <div className="sk">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Channel to topic flow: ${items.map((t) => `${t.label} ${t.videos} videos`).join(", ")}`}>
        <defs>{L.map((n) => <clipPath key={n.id} id={`sk-clip-${n.id}`}><circle cx={XL - 22} cy={n.y + n.h / 2} r={9} /></clipPath>)}</defs>
        <text x={XL + NW / 2} y={10} textAnchor="middle" className="sk__head">CHANNELS</text>
        <text x={XR + NW / 2} y={10} textAnchor="middle" className="sk__head">TOPIC CLUSTERS</text>
        {bands.map((b) => (
          <path key={`${b.f.channel_id}-${b.f.topic_id}`} d={b.d} fill={b.color} className={`sk__band${active(b.f) ? (focus ? " is-on" : "") : " is-dim"}`}>
            <title>{`${b.f.channel_name ?? b.f.channel_id} → ${items.find((t) => t.topic_id === b.f.topic_id)?.label}: ${b.f.videos} videos`}</title>
          </path>
        ))}
        {L.map((n) => {
          const src = icons.get(n.id), id = `c:${n.id}`;
          return (
            <g key={n.id} className={`sk__node${focus && focus !== id && !flows.some((f) => f.channel_id === n.id && active(f)) ? " is-dim" : ""}`} role="button" tabIndex={0}
              aria-label={`${n.name}: ${n.videos} videos`} onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)} onClick={() => onSelect(id)}
              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onSelect(id); } }}>
              <rect x={XL} y={n.y} width={NW} height={n.h} rx={3} className="sk__bar" />
              {src ? <image href={src} x={XL - 31} y={n.y + n.h / 2 - 9} width={18} height={18} clipPath={`url(#sk-clip-${n.id})`} preserveAspectRatio="xMidYMid slice" />
                : <circle cx={XL - 22} cy={n.y + n.h / 2} r={9} fill="#cbd5e1" />}
              <text x={XL - 38} y={n.y + n.h / 2 + 4} textAnchor="end" className="sk__label">{label(n.name)}</text>
            </g>
          );
        })}
        {R.map((t) => {
          const id = `t:${t.topic_id}`, color = TOPIC_COLORS[t.i % TOPIC_COLORS.length];
          return (
            <g key={t.topic_id} className={`sk__node${focus && !flows.some((f) => f.topic_id === t.topic_id && active(f)) ? " is-dim" : ""}`} role="button" tabIndex={0}
              aria-label={`${t.label}: ${t.videos} videos, ${pct(t.share)}`} onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)} onClick={() => onSelect(id)}
              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onSelect(id); } }}>
              <rect x={XR} y={t.y} width={NW} height={t.h} rx={3} fill={color} />
              {t.h >= 30 ? (
                <>
                  <text x={XR + NW + 10} y={t.y + t.h / 2 - 7} className="sk__tlabel">{t.label}</text>
                  <text x={XR + NW + 10} y={t.y + t.h / 2 + 9} className="sk__tsub">{pct(t.share)} · {int(t.videos)} videos</text>
                </>
              ) : (
                <text x={XR + NW + 10} y={t.y + t.h / 2} className="sk__tlabel">{t.label} <tspan className="sk__tsub">{pct(t.share)} · {int(t.videos)}</tspan></text>
              )}
            </g>
          );
        })}
      </svg>
      <p className="xnote">Band width = collected videos from that channel in that topic ({int(total)} in total).</p>
    </div>
  );
}

/** Channels around a wheel; only the strongest content links are drawn so the picture stays readable. */
function SimilarityWheel({ axis, pairs, focus, onSelect }: {
  axis: Ch[];
  pairs: { a: Ch; b: Ch; v: number }[];
  focus?: string;
  onSelect: (id: string) => void;
}) {
  const icons = useContext(ChannelIconContext);
  const W = 820, H = 600, CX = W / 2, CY = H / 2, R = 210;
  const order = axis.map((c) => c.id);
  const pos = new Map(axis.map((c, i) => {
    const a = (-90 + (360 * i) / axis.length) * (Math.PI / 180);
    return [c.id, { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a), a }];
  }));
  const vs = pairs.map((p) => p.v);
  const lo = Math.min(...vs), hi = Math.max(...vs);
  const t = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 1);
  return (
    <div className="sw">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Strongest content links: ${pairs.slice(0, 5).map((p) => `${p.a.label} and ${p.b.label} ${p.v.toFixed(3)}`).join("; ")}`}>
        <defs>
          <radialGradient id="sw-bg"><stop offset="0%" stopColor="#eef2ff" /><stop offset="100%" stopColor="#ffffff" stopOpacity="0" /></radialGradient>
          <linearGradient id="sw-edge" x1="0" x2="1"><stop offset="0%" stopColor="#6366f1" /><stop offset="100%" stopColor="#0ea5e9" /></linearGradient>
          {axis.map((c) => <clipPath key={c.id} id={`sw-clip-${c.id}`}><circle cx={pos.get(c.id)!.x} cy={pos.get(c.id)!.y} r={16} /></clipPath>)}
        </defs>
        <circle cx={CX} cy={CY} r={R + 40} fill="url(#sw-bg)" />
        <circle cx={CX} cy={CY} r={R} className="sw__ring" />
        {pairs.map((p) => {
          const a = pos.get(p.a.id)!, b = pos.get(p.b.id)!;
          const on = focus && (p.a.id === focus || p.b.id === focus);
          const dim = focus && !on;
          return (
            <path key={`${p.a.id}|${p.b.id}`} d={`M${a.x},${a.y} Q${CX + ((a.x + b.x) / 2 - CX) * 0.45},${CY + ((a.y + b.y) / 2 - CY) * 0.45} ${b.x},${b.y}`} className={`sw__edge${on ? " is-on" : ""}${dim ? " is-dim" : ""}`}
              style={{ strokeWidth: 1.5 + 5 * t(p.v) }}>
              <title>{`${p.a.label} · ${p.b.label}: ${p.v.toFixed(3)}`}</title>
            </path>
          );
        })}
        {axis.map((c) => {
          const p = pos.get(c.id)!, src = icons.get(c.id), right = Math.cos(p.a) >= -0.01;
          const lx = CX + (R + 30) * Math.cos(p.a), ly = CY + (R + 30) * Math.sin(p.a);
          const on = focus === c.id, linked = focus && pairs.some((q) => (q.a.id === focus && q.b.id === c.id) || (q.b.id === focus && q.a.id === c.id));
          return (
            <g key={c.id} className={`sw__node${on ? " is-on" : ""}${focus && !on && !linked ? " is-dim" : ""}`} role="button" tabIndex={0}
              aria-label={c.label} onClick={() => onSelect(c.id)}
              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onSelect(c.id); } }}>
              <circle cx={p.x} cy={p.y} r={on ? 24 : 20} className="sw__halo" />
              {src ? <image href={src} x={p.x - 16} y={p.y - 16} width={32} height={32} clipPath={`url(#sw-clip-${c.id})`} preserveAspectRatio="xMidYMid slice" />
                : <><circle cx={p.x} cy={p.y} r={16} fill={colorFor(c.id, order)} /><text x={p.x} y={p.y + 4} textAnchor="middle" className="tnet__init">{initials(c.label)}</text></>}
              <text x={lx} y={ly + 4} textAnchor={Math.abs(Math.cos(p.a)) < 0.2 ? "middle" : right ? "start" : "end"} className="sw__label">{c.label}</text>
            </g>
          );
        })}
      </svg>
      <div className="tnet__legend">
        <span><i className="sw__lg" /> thicker = more similar content</span>
        <span>links shown: {lo.toFixed(3)} – {hi.toFixed(3)} (cosine)</span>
        <span>click a channel to highlight its links</span>
      </div>
    </div>
  );
}

export function TopicsPage() {
  const { snapshotId } = useResearch();
  const [params, setParams] = useSearchParams();
  const sim = useApi((s) => component3Api.topicSimilarity({ snapshotId }, s), [snapshotId]);
  const clusters = useApi((s) => component3Api.topics({ snapshotId }, s), [snapshotId]);

  const lookup = useMemo(() => {
    const m = new Map<string, number | null>();
    if (sim.status === "success") for (const c of sim.data.cells) m.set(`${c.source_channel_id}|${c.destination_channel_id}`, c.topic_similarity);
    return m;
  }, [sim]);
  const value = (a: string, b: string) => lookup.get(`${a}|${b}`) ?? lookup.get(`${b}|${a}`) ?? null;
  const axis: Ch[] = sim.status === "success" ? sim.data.channels.map((c) => ({ id: c.channel_id, label: c.channel_name ?? c.channel_id })) : [];
  const order = axis.map((c) => c.id);
  const allPairs = axis.flatMap((a, i) => axis.slice(i + 1).map((b) => ({ a, b, v: value(a.id, b.id) })))
    .filter((p): p is { a: Ch; b: Ch; v: number } => p.v !== null).sort((x, y) => y.v - x.v);
  const vals = allPairs.map((p) => p.v);
  const meanSim = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  const central = new Map(axis.map((c) => {
    const vs = axis.filter((o) => o.id !== c.id).map((o) => value(c.id, o.id)).filter((v): v is number => v !== null);
    return [c.id, vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : 0];
  }));
  const selectedChannel = params.get("channel") ?? undefined;
  const selectedTopic = params.get("topic") ?? undefined;
  const mapSel = selectedChannel ? `c:${selectedChannel}` : selectedTopic ? `t:${selectedTopic}` : "";
  const items = clusters.status === "success" ? clusters.data.items : [];
  const topic = items.find((t) => t.topic_id === selectedTopic);
  const topicIndex = items.findIndex((t) => t.topic_id === selectedTopic);
  const chName = axis.find((c) => c.id === selectedChannel)?.label;
  const neighbours = selectedChannel ? axis.filter((c) => c.id !== selectedChannel).map((c) => ({ ...c, v: value(selectedChannel, c.id) }))
    .filter((c): c is Ch & { v: number } => c.v !== null).sort((a, b) => b.v - a.v) : [];
  const nbLo = neighbours.length ? neighbours[neighbours.length - 1].v : 0, nbHi = neighbours[0]?.v ?? 1;
  const close = () => setParams({});
  const pickMap = (id: string) => (id === mapSel ? close() : setParams(id.startsWith("t:") ? { topic: id.slice(2) } : { channel: id.slice(2) }));
  const pickChannel = (id: string) => (id === selectedChannel ? close() : setParams({ channel: id }));

  return (
    <>
      {sim.status === "loading" && <Loading variant="graph" label="Loading topic similarity…" />}
      {sim.status === "error" && <ErrorState error={sim.error} onRetry={sim.reload} what="Topic similarity" />}
      {sim.status === "success" && (
        <div className="gx">
          <section className="xhero gx__hero" aria-label="Topic run">
            <span className="gx__mark gx__mark--topic" aria-hidden="true"><Icon name="tag" size={32} /></span>
            <div className="xhero__id">
              <h1>Topic intelligence</h1>
              <p>What the channels publish, from embeddings of video titles and descriptions · model <code>{sim.data.model ?? "—"}</code> · {date(sim.data.created_at)}</p>
              <ul className="tp-tags"><li>symmetric (A·B = B·A)</li><li>content, not audience</li><li>unlabelled topics</li></ul>
            </div>
            <div className="xhero__facts">
              <div><strong>{int(sim.data.channels.filter((c) => c.profile_available).length)}/{int(sim.data.channels.length)}</strong><span>channel profiles</span></div>
              <div><strong>{int(sim.data.n_topics)}</strong><span>topic clusters</span></div>
              <div><strong>{num(meanSim, 3)}</strong><span>mean similarity</span></div>
            </div>
          </section>

          <Block title="Channel → topic flow" label="Topic map" hint="Each channel's videos across the topic clusters.">
            {clusters.status === "loading" && <Loading variant="graph" />}
            {clusters.status === "error" && <ErrorState error={clusters.error} onRetry={clusters.reload} what="Topic clusters" />}
            {clusters.status === "success" && <TopicFlow items={items} flows={clusters.data.flows ?? []} axis={axis} selected={mapSel} onSelect={pickMap} />}
          </Block>

          <Block title="Content similarity wheel" hint="The 12 most content-similar channel pairs.">
            <div className="sw-wrap">
              <SimilarityWheel axis={axis} focus={selectedChannel} onSelect={pickChannel}
                pairs={[...allPairs.slice(0, 12), ...(selectedChannel ? allPairs.filter((p) => (p.a.id === selectedChannel || p.b.id === selectedChannel)).slice(0, 3) : [])]
                  .filter((p, i, arr) => arr.findIndex((q) => q.a.id === p.a.id && q.b.id === p.b.id) === i)} />
              <ol className="sw-list" aria-label="Strongest content links">
                {allPairs.slice(0, 12).map((p, i) => {
                  const on = selectedChannel && (p.a.id === selectedChannel || p.b.id === selectedChannel);
                  return (
                    <li key={`${p.a.id}|${p.b.id}`} className={on ? "is-on" : ""}>
                      <span className="sw-list__n">{i + 1}</span>
                      <span className="pairicons" aria-hidden="true">
                        <ChannelAvatar id={p.a.id} name={p.a.label} order={order} size={22} />
                        <ChannelAvatar id={p.b.id} name={p.b.label} order={order} size={22} />
                      </span>
                      <span className="sw-list__who"><b>{p.a.label}</b><small>{p.b.label}</small></span>
                      <b className="sw-list__v">{p.v.toFixed(3)}</b>
                    </li>
                  );
                })}
              </ol>
            </div>
          </Block>

          <Block title="Topic similarity matrix" hint="Content similarity (cosine) of every channel pair.">
            <Heatmap axis={axis} value={value} selected={selectedChannel} onSelect={pickChannel} caption="Topic similarity between research channels" />
          </Block>

          {selectedChannel && chName && (
            <section className="xblock step-panel" aria-label={`Most similar to ${chName}`}>
              <header className="xblock__head">
                <div className="tm-drawer__id"><ChannelAvatar id={selectedChannel} name={chName} order={order} size={36} /><div><h3>{chName}</h3><p>centrality {num(central.get(selectedChannel) ?? null, 3)}</p></div></div>
                <button type="button" className="link-button" onClick={close}>Close</button>
              </header>
              <h4 className="gx__sub">Most similar to {chName}</h4>
              <ol className="tm-nb">
                {neighbours.slice(0, 8).map((c) => (
                  <li key={c.id}>
                    <button type="button" onClick={() => pickChannel(c.id)}><ChannelAvatar id={c.id} name={c.label} order={order} size={22} /><span>{c.label}</span></button>
                    <span className="tm-nb__bar"><i style={{ width: `${Math.max(6, ((c.v - nbLo) / Math.max(1e-9, nbHi - nbLo)) * 100)}%` }} /></span>
                    <b>{c.v.toFixed(3)}</b>
                  </li>
                ))}
              </ol>
              <h4 className="gx__sub">Least alike</h4>
              <ul className="tp-least">
                {neighbours.slice(-2).reverse().map((c) => <li key={c.id}><ChannelAvatar id={c.id} name={c.label} order={order} size={22} /><span>{c.label}</span><b>{c.v.toFixed(3)}</b></li>)}
              </ul>
              <p className="small"><Link to={`/channels?channel=${encodeURIComponent(selectedChannel)}`}>Open in Channel Explorer →</Link></p>
            </section>
          )}
          {topic && (
            <section className="xblock step-panel" aria-label={topic.label} style={{ ["--c" as string]: TOPIC_COLORS[topicIndex % TOPIC_COLORS.length] }}>
              <header className="xblock__head">
                <div className="tm-drawer__id"><span className="tm-card__badge tm-card__badge--lg">{topicIndex + 1}</span><div><h3>{topic.label}</h3><p>unlabelled cluster of video text</p></div></div>
                <button type="button" className="link-button" onClick={close}>Close</button>
              </header>
              <ul className="model__chips">
                <li><span>Share of videos</span><b>{pct(topic.share)}</b></li>
                <li><span>Videos</span><b>{int(topic.videos)}</b></li>
                <li><span>Views</span><b>{compactN(topic.views)}</b></li>
                <li><span>Leading channel</span><b>{topic.top_channel_name ?? "—"}</b></li>
              </ul>
              <div className="tm-share"><i style={{ width: `${(topic.share ?? 0) * 100}%` }} /></div>
              <p className="small muted">Topic clusters are unlabelled KMeans clusters of video text embeddings; the numbers are cluster sizes, not trends.</p>
            </section>
          )}
          <Provenance snapshotId={sim.data.snapshot_id} extra={sim.data.experiment_id ? `Topic run ${sim.data.experiment_id}` : undefined} />
        </div>
      )}
    </>
  );
}
