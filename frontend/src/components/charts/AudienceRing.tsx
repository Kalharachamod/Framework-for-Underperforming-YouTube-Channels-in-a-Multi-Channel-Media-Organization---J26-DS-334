/**
 * Radial audience network: every channel sits on a ring; a curve joins two channels that share
 * commenters (width and opacity follow the aggregate count). Channels without any shared commenter are
 * drawn hollow. Hovering or focusing a channel isolates its connections. Shared commenters are an
 * aggregate co-commenting signal, not audience movement.
 */
import { useMemo, useState } from "react";

export interface RingNode { id: string; label: string; value: number }
export interface RingEdge { a: string; b: string; weight: number }

const S = 860, C = S / 2, R = 262;
const short = (s: string, n = 17) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const k = (v: number) => (v >= 1e4 ? `${Math.round(v / 1e3)}K` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : String(v));

export function AudienceRing({ nodes, edges, accentPair, centerValue, centerLabel }: {
  nodes: RingNode[]; edges: RingEdge[]; accentPair?: [string, string]; centerValue: string; centerLabel: string;
}) {
  const [active, setActive] = useState<string | null>(null);
  const layout = useMemo(() => {
    const ordered = [...nodes].sort((p, q) => q.value - p.value);
    const pos = new Map(ordered.map((n, i) => {
      const a = (2 * Math.PI * i) / ordered.length - Math.PI / 2;
      return [n.id, { a, x: C + R * Math.cos(a), y: C + R * Math.sin(a) }];
    }));
    const maxV = Math.max(1, ...nodes.map((n) => n.value));
    const maxW = Math.max(1, ...edges.map((e) => e.weight));
    const degree = new Map<string, { n: number; total: number }>();
    for (const e of edges) for (const id of [e.a, e.b]) {
      const d = degree.get(id) ?? { n: 0, total: 0 };
      degree.set(id, { n: d.n + 1, total: d.total + e.weight });
    }
    return { ordered, pos, maxV, maxW, degree };
  }, [nodes, edges]);

  const isAccent = (e: RingEdge) => !!accentPair && ((e.a === accentPair[0] && e.b === accentPair[1]) || (e.a === accentPair[1] && e.b === accentPair[0]));
  const touches = (e: RingEdge) => active !== null && (e.a === active || e.b === active);
  const neighbours = new Set(active ? edges.filter(touches).flatMap((e) => [e.a, e.b]) : []);
  const activeNode = active ? nodes.find((n) => n.id === active) : undefined;
  const activeDeg = active ? layout.degree.get(active) : undefined;
  const summary = `Audience network of ${nodes.length} channels: ${edges.length} channel pairs share commenters. `
    + [...edges].sort((p, q) => q.weight - p.weight).slice(0, 5)
      .map((e) => `${nodes.find((n) => n.id === e.a)?.label} and ${nodes.find((n) => n.id === e.b)?.label}: ${e.weight}`).join("; ");

  return (
    <figure className="ring" aria-label={summary}>
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-hidden="true">
        <circle cx={C} cy={C} r={R} className="ring__orbit" />
        {[...edges].sort((p, q) => p.weight - q.weight).map((e) => {
          const p = layout.pos.get(e.a), q = layout.pos.get(e.b);
          if (!p || !q) return null;
          const t = e.weight / layout.maxW;
          const on = touches(e), accent = isAccent(e);
          const cls = active ? (on ? "ring__edge ring__edge--on" : "ring__edge ring__edge--off") : accent ? "ring__edge ring__edge--accent" : "ring__edge";
          return (
            <path key={`${e.a}-${e.b}`} d={`M${p.x},${p.y} Q${C},${C} ${q.x},${q.y}`} className={cls}
              strokeWidth={0.8 + 7 * t} strokeOpacity={active ? undefined : accent ? 0.95 : 0.1 + 0.45 * t} />
          );
        })}
        {layout.ordered.map((n) => {
          const p = layout.pos.get(n.id)!;
          const left = Math.cos(p.a) < -1e-6;
          const deg = (p.a * 180) / Math.PI + (left ? 180 : 0);
          const lx = C + (R + 20) * Math.cos(p.a), ly = C + (R + 20) * Math.sin(p.a);
          const r = 3.5 + 7 * Math.sqrt(n.value / layout.maxV);
          const isolated = !layout.degree.has(n.id);
          const dim = active !== null && active !== n.id && !neighbours.has(n.id);
          const accent = accentPair?.includes(n.id) && !active;
          return (
            <g key={n.id} className={`ring__node${dim ? " is-dim" : ""}${active === n.id ? " is-active" : ""}${accent ? " is-accent" : ""}`}
              tabIndex={0} role="button" aria-label={`${n.label}: ${n.value} unique commenters`}
              onMouseEnter={() => setActive(n.id)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(n.id)} onBlur={() => setActive(null)}>
              <circle cx={p.x} cy={p.y} r={r + 10} className="ring__hit" />
              <circle cx={p.x} cy={p.y} r={r} className={isolated ? "ring__dot ring__dot--hollow" : "ring__dot"} />
              <text x={lx} y={ly} dy="0.35em" textAnchor={left ? "end" : "start"} transform={`rotate(${deg} ${lx} ${ly})`} className="ring__label">
                {short(n.label)}
              </text>
            </g>
          );
        })}
        <g className="ring__center" aria-hidden="true">
          {activeNode ? (
            <>
              <text x={C} y={C - 24} textAnchor="middle" className="ring__center-name">{short(activeNode.label, 26)}</text>
              <text x={C} y={C + 18} textAnchor="middle" className="ring__center-value">{k(activeDeg?.total ?? 0)}</text>
              <text x={C} y={C + 44} textAnchor="middle" className="ring__center-label">
                {activeDeg ? `shared with ${activeDeg.n} channel${activeDeg.n > 1 ? "s" : ""}` : "no shared commenters"}
              </text>
            </>
          ) : (
            <>
              <text x={C} y={C + 12} textAnchor="middle" className="ring__center-value">{centerValue}</text>
              <text x={C} y={C + 40} textAnchor="middle" className="ring__center-label">{centerLabel}</text>
            </>
          )}
        </g>
      </svg>
    </figure>
  );
}

/** Minimal area sparkline for small multiples (own scale per panel, zero baseline). */
export function MiniArea({ values, label }: { values: (number | null)[]; label: string }) {
  const W = 200, H = 52, max = Math.max(1, ...values.map((v) => v ?? 0));
  if (values.length < 2) return null;
  const pts = values.map((v, i) => `${(i * W) / (values.length - 1)},${H - 2 - ((v ?? 0) / max) * (H - 6)}`);
  return (
    <svg className="mini-area" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <path d={`M0,${H} L${pts.join(" L")} L${W},${H} Z`} className="mini-area__fill" />
      <polyline points={pts.join(" ")} className="mini-area__line" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
