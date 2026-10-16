/**
 * metapath2vec as a neural network, in three panels: the stored metapaths as walk tracks (share of all
 * walks), an example walk with its sliding window, and the skip-gram network drawn as a fan (input node →
 * embedding vector → context nodes on an arc, positives and sampled negatives). Window, negatives,
 * dimensions, walk length and walk counts come from the stored run; the example walk and the drawn
 * neurons are schematic.
 */
import type { MetapathWalks } from "../../features/component_3/types";

const COLORS: Record<string, string> = { channel: "#2563eb", video: "#f43f5e", commenter: "#8b5cf6", topic: "#f59e0b" };
const W = 1120, H = 440;
const abbrev = (t: string) => (t === "channel" ? "Ch" : t[0].toUpperCase());

export function SkipGram({ metapaths, window, negative, dims, walkLength }: {
  metapaths: MetapathWalks[];
  window: number | null;
  negative: number | null;
  dims: number | null;
  walkLength: number | null;
}) {
  const sum = metapaths.reduce((a, m) => a + (m.walks ?? 0), 0) || 1;
  const pattern = metapaths[0]?.node_types ?? ["commenter", "video", "channel", "video", "commenter"];
  const cycle = pattern.length > 1 ? pattern.slice(0, -1) : pattern;
  const walk = Array.from({ length: 9 }, (_, i) => cycle[i % cycle.length]);
  const centre = 4;
  const half = Math.max(1, Math.min(4, Math.floor((window ?? 2) / 2) || 1));
  const inWin = (i: number) => Math.abs(i - centre) <= half;
  const centreType = walk[centre];

  // panel 2: example walk on a gentle wave
  const WX = 344, WY = 210, WS = 34;
  const wp = walk.map((t, i) => ({ t, x: WX + i * WS, y: WY + Math.sin(i * 0.9) * 22 }));

  // panel 3: fan network
  const IN = { x: 742, y: 220 }, VX = 830, VY0 = 116, VH = 208, cells = 16;
  const ctxIds = walk.map((t, i) => ({ t, i })).filter((w) => w.i !== centre && inWin(w.i));
  const negs = Math.max(1, Math.min(4, negative ?? 2));
  const negTypes = ["video", "channel", "topic", "commenter"].slice(0, negs);
  const targets = [...ctxIds.map((c) => ({ t: c.t, pos: true })), ...negTypes.map((t) => ({ t, pos: false }))];
  const arc = targets.map((x, k) => {
    const ang = (-62 + (124 * k) / Math.max(1, targets.length - 1)) * (Math.PI / 180);
    return { ...x, x: 880 + 120 * Math.cos(ang), y: 222 + 140 * Math.sin(ang) };
  });

  const summary = `metapath2vec skip-gram: ${metapaths.length} metapaths, window ${window ?? "?"}, ${negative ?? "?"} negative samples, ${dims ?? "?"}-dimensional embedding.`;

  return (
    <figure className="hn">
      <div className="hf__scroll sg">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
          <defs>
            <linearGradient id="sg-win" x1="0" x2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity="0" />
              <stop offset="20%" stopColor="#22c55e" stopOpacity="0.16" />
              <stop offset="80%" stopColor="#22c55e" stopOpacity="0.16" />
              <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
            </linearGradient>
            <radialGradient id="sg-in" cx="35%" cy="30%" r="75%">
              <stop offset="0%" stopColor="#fff" stopOpacity="0.55" />
              <stop offset="45%" stopColor={COLORS[centreType] ?? "#6366f1"} />
            </radialGradient>
          </defs>

          {/* panel titles */}
          {[[150, "1 · Metapath walks", `${metapaths.length} metapaths · ${sum.toLocaleString("en-US")} walks`],
            [480, "2 · Sliding window", `window ${window ?? "—"} · walk length ${walkLength ?? "—"}`],
            [890, "3 · Skip-gram network", `${dims ?? "—"}-dim embedding · ${negative ?? "—"} negatives`]].map(([x, t, s]) => (
            <g key={String(t)}>
              <text x={Number(x)} y={30} textAnchor="middle" className="hf__title">{t}</text>
              <text x={Number(x)} y={48} textAnchor="middle" className="hf__sub">{s}</text>
            </g>
          ))}
          <line x1={304} y1={74} x2={304} y2={H - 30} className="sg__divider" />
          <line x1={664} y1={74} x2={664} y2={H - 30} className="sg__divider" />

          {/* 1 · walk tracks */}
          {metapaths.slice(0, 6).map((m, i) => {
            const y = 96 + i * 58, share = (m.walks ?? 0) / sum;
            return (
              <g key={m.metapath}>
                <rect x={16} y={y - 18} width={272} height={48} rx={14} className="sg__track" />
                {m.node_types.map((t, k) => (
                  <g key={k}>
                    {k > 0 && <line x1={36 + (k - 1) * 24} y1={y} x2={36 + k * 24} y2={y} stroke="#cbd5e1" strokeWidth={2} />}
                    <circle cx={36 + k * 24} cy={y} r={9} fill={COLORS[t] ?? "#94a3b8"} stroke="#fff" strokeWidth={1.5} />
                    <text x={36 + k * 24} y={y + 3.5} textAnchor="middle" className="sg__node">{abbrev(t)}</text>
                  </g>
                ))}
                <text x={276} y={y + 4} textAnchor="end" className="sg__share">{Math.round(share * 100)}%</text>
                <rect x={28} y={y + 16} width={248} height={5} rx={2.5} fill="#eef2ff" />
                <rect x={28} y={y + 16} width={Math.max(4, 248 * share)} height={5} rx={2.5} fill="#6366f1" />
                <text x={236} y={y + 4} textAnchor="end" className="hf__small">{(m.walks ?? 0).toLocaleString("en-US")}</text>
              </g>
            );
          })}

          {/* 2 · example walk with window */}
          <rect x={wp[centre - half].x - 18} y={WY - 50} width={(2 * half) * WS + 36} height={100} rx={22} fill="url(#sg-win)" stroke="#86efac" strokeDasharray="4 4" />
          <path d={wp.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ")} fill="none" stroke="#cbd5e1" strokeWidth={2} />
          {wp.map((p, i) => (
            <g key={i} opacity={inWin(i) ? 1 : 0.4}>
              {i === centre && <circle cx={p.x} cy={p.y} r={17} fill="none" stroke={COLORS[p.t]} strokeWidth={2.5} />}
              <circle cx={p.x} cy={p.y} r={i === centre ? 12 : 9} fill={COLORS[p.t] ?? "#94a3b8"} stroke="#fff" strokeWidth={2} />
              <text x={p.x} y={p.y + 3.5} textAnchor="middle" className="sg__node">{abbrev(p.t)}</text>
            </g>
          ))}
          <text x={wp[centre].x} y={WY + 78} textAnchor="middle" className="hf__small">centre node predicts the {ctxIds.length} neighbours in its window</text>
          <text x={wp[centre].x} y={WY + 96} textAnchor="middle" className="hf__tiny">example walk along {metapaths[0]?.metapath ?? "a metapath"}</text>

          {/* 3 · fan network */}
          {Array.from({ length: cells }, (_, k) => {
            const y = VY0 + (VH * (k + 0.5)) / cells;
            return <path key={`iv${k}`} d={`M${IN.x},${IN.y} C${IN.x + 40},${IN.y} ${VX - 40},${y} ${VX - 12},${y}`} className="sg__wire" />;
          })}
          {arc.map((a, k) => (
            <path key={`va${k}`} d={`M${VX + 12},${VY0 + VH / 2} C${VX + 70},${VY0 + VH / 2} ${a.x - 70},${a.y} ${a.x - 14},${a.y}`}
              className={a.pos ? "sg__wire sg__wire--pos" : "sg__wire sg__wire--neg"} />
          ))}
          <circle cx={IN.x} cy={IN.y} r={22} className="sg__inhalo" />
          <circle cx={IN.x} cy={IN.y} r={15} fill="url(#sg-in)" stroke="#fff" strokeWidth={2.5} className="sg__in" />
          <text x={IN.x} y={IN.y + 4} textAnchor="middle" className="sg__node sg__node--lg">{abbrev(centreType)}</text>
          <text x={IN.x} y={IN.y + 44} textAnchor="middle" className="hf__small">input node</text>
          <text x={IN.x} y={IN.y + 58} textAnchor="middle" className="hf__tiny">one-hot</text>

          <rect x={VX - 12} y={VY0 - 6} width={24} height={VH + 12} rx={12} className="sg__vecbox" />
          {Array.from({ length: cells }, (_, k) => (
            <rect key={`c${k}`} x={VX - 8} y={VY0 + (VH * k) / cells + 1.5} width={16} height={VH / cells - 3} rx={3}
              fill="#0ea5e9" opacity={0.3 + 0.7 * (((k * 7) % cells) / cells)} />
          ))}
          <text x={VX} y={VY0 + VH + 30} textAnchor="middle" className="hf__small">{dims ?? "—"}-value embedding</text>

          {arc.map((a, k) => (
            <g key={`t${k}`}>
              <circle cx={a.x} cy={a.y} r={13} fill={COLORS[a.t]} stroke={a.pos ? "#22c55e" : "#f43f5e"} strokeWidth={3} />
              <text x={a.x} y={a.y + 3.5} textAnchor="middle" className="sg__node">{abbrev(a.t)}</text>
              <text x={a.x + 20} y={a.y + 4} className={a.pos ? "sg__lbl sg__lbl--pos" : "sg__lbl sg__lbl--neg"}>{a.pos ? "context · 1" : "negative · 0"}</text>
            </g>
          ))}
          <text x={880} y={H - 18} textAnchor="middle" className="hf__small">score per node: σ(⟨u, v⟩)</text>
        </svg>
      </div>
      <figcaption className="nn__caption">
        Walks follow each metapath; within a window of {window ?? "—"}, the centre node is trained to score its window neighbours high (green ring)
        and {negative ?? "—"} randomly sampled nodes low (red ring). The trained weights are the {dims ?? "—"}-dimensional embeddings; channel embeddings are
        compared by cosine similarity in the score. Walk counts and settings are from the stored run; the example walk and drawn nodes are schematic.
      </figcaption>
    </figure>
  );
}
