/**
 * Overlap visuals built only from the overlap API response.
 * - VennDiagram: the top channels by unique commenters as overlapping circles around a centre badge with the
 *   real number of commenters seen on 2+ channels. The layout is illustrative (overlap areas are NOT to
 *   scale); every number shown is exact.
 * - HubNetwork: the channel with the most shared commenters in the centre, the strongest-connected channels
 *   around it; edge width/opacity ~ shared commenters, strength classes are terciles of the shown edges.
 */
import { initials } from "../common/ChannelAvatar";

export interface OverlapChannel {
  id: string;
  label: string;
  value: number; // unique commenters
  color: string;
}

export interface OverlapLink {
  a: string;
  b: string;
  weight: number; // shared commenters
}

const short = (s: string, n = 18) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const k = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e4 ? `${Math.round(v / 1e3)}K` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : String(v));

/** `compact` enlarges text and shortens names for narrow panels (the SVG is scaled down there). */
export function VennDiagram({ channels, shared, max = 6, compact = false, labelChars = 18 }: { channels: OverlapChannel[]; shared: number; max?: number; compact?: boolean; labelChars?: number }) {
  const top = [...channels].sort((p, q) => q.value - p.value).slice(0, max);
  const W = 560, H = 440, cx = W / 2, cy = H / 2, d = 62, r = 100, lr = 182;
  const summary = `Top ${top.length} channels by unique commenters: ${top.map((t) => `${t.label} ${t.value}`).join(", ")}; ${shared} commenters seen on 2 or more channels.`;
  return (
    <figure className={compact ? "venn venn--compact" : "venn"} aria-label={summary}>
      <svg viewBox={compact ? `${cx - 172} ${cy - 172} 344 344` : `0 -16 ${W} ${H + 24}`} role="img" aria-hidden="true">
        {top.map((t, i) => {
          const a = (2 * Math.PI * i) / top.length - Math.PI / 2;
          return <circle key={t.id} cx={cx + d * Math.cos(a)} cy={cy + d * Math.sin(a)} r={r} fill={t.color} fillOpacity={0.16} stroke={t.color} strokeOpacity={0.35} />;
        })}
        {top.map((t, i) => {
          const a = (2 * Math.PI * i) / top.length - Math.PI / 2;
          const anchor = Math.cos(a) > 0.3 ? "start" : Math.cos(a) < -0.3 ? "end" : "middle";
          // labels just outside the circle; top/bottom labels sit above/below so they never cover the badge
          const x = cx + lr * Math.cos(a), y = cy + lr * Math.sin(a) + (Math.sin(a) < -0.5 ? -22 : Math.sin(a) > 0.5 ? 14 : 0);
          const bx = cx + (d + r - 30) * Math.cos(a), by = cy + (d + r - 30) * Math.sin(a);
          return (
            <g key={`l${t.id}`}>
              <circle cx={bx} cy={by} r={13} fill={t.color} stroke="#fff" strokeWidth={2} />
              <text x={bx} y={by + 4} textAnchor="middle" className="venn__initials">{initials(t.label)}</text>
              {!compact && (
                <>
                  <text x={x} y={y - 8} textAnchor={anchor} className="venn__name">{short(t.label, labelChars)}</text>
                  <text x={x} y={y + 9} textAnchor={anchor} className="venn__value">{k(t.value)}</text>
                  <text x={x} y={y + 22} textAnchor={anchor} className="venn__sub">unique commenters</text>
                </>
              )}
            </g>
          );
        })}
        <rect x={cx - 62} y={cy - 26} width={124} height={52} rx={10} className="venn__badge" />
        <text x={cx} y={cy - 2} textAnchor="middle" className="venn__badge-value">{k(shared)}</text>
        <text x={cx} y={cy + 15} textAnchor="middle" className="venn__badge-sub">on 2+ channels</text>
      </svg>
      {compact && (
        <ul className="venn__legend">
          {top.map((t) => (
            <li key={t.id}><span className="venn__dot" style={{ background: t.color }} /><span className="venn__legend-name">{t.label}</span><span className="venn__legend-value">{k(t.value)}</span></li>
          ))}
          <li className="venn__legend-note">unique commenters per channel</li>
        </ul>
      )}
    </figure>
  );
}

export function HubNetwork({ channels, links, max = 7 }: { channels: OverlapChannel[]; links: OverlapLink[]; max?: number }) {
  const degree = new Map<string, number>();
  for (const l of links) {
    degree.set(l.a, (degree.get(l.a) ?? 0) + l.weight);
    degree.set(l.b, (degree.get(l.b) ?? 0) + l.weight);
  }
  const ranked = channels.filter((c) => (degree.get(c.id) ?? 0) > 0).sort((p, q) => (degree.get(q.id) ?? 0) - (degree.get(p.id) ?? 0)).slice(0, max);
  if (ranked.length < 2) return <p className="muted">Too few connected channels to draw a network.</p>;
  const [hub, ...ring] = ranked;
  const ids = new Set(ranked.map((c) => c.id));
  const shown = links.filter((l) => ids.has(l.a) && ids.has(l.b)).sort((p, q) => q.weight - p.weight);
  const ws = shown.map((l) => l.weight).sort((p, q) => p - q);
  const t1 = ws[Math.floor(ws.length / 3)] ?? 0, t2 = ws[Math.floor((2 * ws.length) / 3)] ?? 0;
  const maxW = Math.max(1, ...ws);
  const W = 460, H = 330, cx = W / 2, cy = H / 2 + 4;
  const pos = new Map<string, { x: number; y: number }>([[hub.id, { x: cx, y: cy }]]);
  ring.forEach((c, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / ring.length;   // evenly around the hub
    pos.set(c.id, { x: cx + 165 * Math.cos(a), y: cy + 118 * Math.sin(a) });
  });
  const col = new Map(ranked.map((c) => [c.id, c.color]));
  const summary = `${hub.label} has the most shared commenters; links: ${shown.slice(0, 5).map((l) => `${channels.find((c) => c.id === l.a)?.label} and ${channels.find((c) => c.id === l.b)?.label} ${l.weight}`).join("; ")}.`;
  return (
    <div className="hub">
      <figure className="hub__graph" aria-label={summary}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-hidden="true">
          <defs>
            <filter id="hub-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          {shown.map((l) => {
            const p = pos.get(l.a)!, q = pos.get(l.b)!;
            const mx = (p.x + q.x) / 2 + (cy - (p.y + q.y) / 2) * 0.15, my = (p.y + q.y) / 2 - 18;
            return <path key={`${l.a}-${l.b}`} d={`M${p.x},${p.y} Q${mx},${my} ${q.x},${q.y}`} fill="none" stroke={col.get(l.a)}
              strokeOpacity={0.25 + 0.6 * (l.weight / maxW)} strokeWidth={1.5 + 9 * (l.weight / maxW)} strokeLinecap="round" />;
          })}
          {ranked.map((c) => {
            const p = pos.get(c.id)!;
            const r = c.id === hub.id ? 30 : 20;
            return (
              <g key={c.id}>
                <circle cx={p.x} cy={p.y} r={r} fill={c.color} filter="url(#hub-glow)" stroke="#fff" strokeWidth={3} />
                <text x={p.x} y={p.y + 4} textAnchor="middle" className="hub__initials">{initials(c.label)}</text>
                <text x={p.x} y={p.y + r + 15} textAnchor="middle" className={c.id === hub.id ? "hub__label hub__label--hub" : "hub__label"}>{short(c.label, 22)}</text>
              </g>
            );
          })}
        </svg>
      </figure>
      <div className="hub__legend" aria-label="Connection strength">
        <strong>Connection strength</strong>
        <span><i className="hub__line hub__line--strong" /> Strong (≥ {t2} shared)</span>
        <span><i className="hub__line hub__line--medium" /> Medium (≥ {t1})</span>
        <span><i className="hub__line hub__line--weak" /> Weak</span>
      </div>
    </div>
  );
}
