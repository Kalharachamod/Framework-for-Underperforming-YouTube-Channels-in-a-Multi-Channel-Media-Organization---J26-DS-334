/**
 * The HGT run as a radial neural network: our recorded input features on the outer ring (grouped and
 * coloured by node type), the type projection and the HGT layers as inner rings (attention heads as arcs),
 * and the channel embedding in the centre, linked to the training decoder and to its use in the score.
 * Feature names, sizes, heads, dropout and dimensions come from the stored run; inner rings draw a few
 * neurons and the key gives the true sizes. Each neuron is linked to its nearest neurons on the next ring
 * (a readable sketch of the dense layers, not every weight).
 */
import { useState } from "react";
import { label as pretty } from "../../utils/format";
import { Icon } from "../common/Icon";

const COLORS: Record<string, string> = { channel: "#2563eb", video: "#f43f5e", commenter: "#8b5cf6", topic: "#f59e0b" };
const INNER = { proj: "#6366f1", l1: "#a855f7", l2: "#d946ef" };
const ORDER = ["channel", "video", "commenter", "topic"];
const W = 1120, H = 640, CX = 410, CY = 320;
const RING = { input: 205, proj: 150, l1: 104, l2: 62, emb: 32 };
const short = (f: string) => pretty(f.replace(/^observed_/, "").replace(/_api_/, "_").replace(/^api_/, ""));
const rad = (d: number) => (d * Math.PI) / 180;
const polar = (r: number, deg: number) => ({ x: CX + r * Math.cos(rad(deg)), y: CY + r * Math.sin(rad(deg)) });
const arc = (r: number, a0: number, a1: number) => {
  const p = polar(r, a0), q = polar(r, a1);
  return `M${p.x},${p.y} A${r},${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${q.x},${q.y}`;
};
const angDiff = (a: number, b: number) => Math.abs(((a - b + 540) % 360) - 180);

/** Soft curved link between two rings, bending slightly towards the centre. */
function link(r1: number, a1: number, r2: number, a2: number) {
  const p = polar(r1, a1), q = polar(r2, a2), m = polar((r1 + r2) / 2 - 6, (a1 + a2) / 2 + (angDiff(a1, a2) > 180 ? 180 : 0));
  return `M${p.x},${p.y} Q${m.x},${m.y} ${q.x},${q.y}`;
}

export function HgtRadial({ features, hidden, layers, heads, dropout, dims }: {
  features: Record<string, string[]>;
  hidden: number | null;
  layers: number;
  heads: number;
  dropout: number | null;
  dims: number | null;
}) {
  const types = ORDER.filter((t) => t in features);
  const total = types.reduce((a, t) => a + features[t].length, 0) || 1;
  const gap = 10, step = (360 - gap * types.length) / total;
  const inputs: { t: string; f: string; a: number }[] = [];
  const groups: { t: string; a0: number; a1: number }[] = [];
  let a = -90 + gap / 2;
  for (const t of types) {
    const a0 = a;
    for (const f of features[t]) { inputs.push({ t, f, a: a + step / 2 }); a += step; }
    groups.push({ t, a0, a1: a });
    a += gap;
  }
  const ring = (n: number, offset = 0) => Array.from({ length: n }, (_, i) => -90 + offset + (360 * (i + 0.5)) / n);
  const proj = ring(10), l1 = ring(8, 11), l2 = ring(8, -11);
  const h = Math.max(1, Math.min(4, heads));
  const nearest = (x: number, to: number[], k: number) => [...to].sort((p, q) => angDiff(x, p) - angDiff(x, q)).slice(0, k);

  // highlighted node type: its input neurons, links and labels stand out, everything else fades
  const [active, setActive] = useState<string | null>(null);
  const on = (t: string) => (active === null || active === t ? "" : " is-dim");
  const hover = (t: string) => ({ onMouseEnter: () => setActive(t), onMouseLeave: () => setActive(null) });
  // projection neurons reached by the highlighted type's inputs (for the inner highlight)
  const litProj = new Set(active ? inputs.filter((i) => i.t === active).flatMap((i) => nearest(i.a, proj, 2)) : []);
  const summary = `HGT on the research graph: ${types.map((t) => `${t} ${features[t].length} features`).join(", ")}; type projection to ${hidden ?? "?"}; `
    + `${layers} layers with ${heads} attention heads; ${dims ?? "?"}-dimensional channel embedding; decoder dot product.`;
  const outA = { x: 862, y: 210 }, outB = { x: 862, y: 410 };

  return (
    <figure className="hn">
      <div className="hr-filter" role="group" aria-label="Highlight a node type">
        <span>Highlight</span>
        <button type="button" aria-pressed={active === null} onClick={() => setActive(null)}>All</button>
        {types.map((t) => (
          <button key={t} type="button" aria-pressed={active === t} onClick={() => setActive(active === t ? null : t)} style={{ ["--c" as string]: COLORS[t] }}>
            <i />{t} · {features[t].length}
          </button>
        ))}
      </div>
      <div className={`hf__scroll hr${active ? " hr--focus" : ""}`}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
          <defs>
            <radialGradient id="hr-bg" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#eef2ff" />
              <stop offset="70%" stopColor="#f8fafc" />
              <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="hr-core" cx="35%" cy="30%" r="75%">
              <stop offset="0%" stopColor="#7dd3fc" />
              <stop offset="100%" stopColor="#0284c7" />
            </radialGradient>
            <radialGradient id="hr-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
            </radialGradient>
            {Object.entries({ ...COLORS, proj: "#6366f1", l1: "#8b5cf6", l2: "#c026d3" }).map(([k, c]) => (
              <radialGradient key={k} id={`hr-n-${k}`} cx="35%" cy="30%" r="75%">
                <stop offset="0%" stopColor="#fff" stopOpacity="0.55" />
                <stop offset="45%" stopColor={c} />
                <stop offset="100%" stopColor={c} />
              </radialGradient>
            ))}
          </defs>

          {/* soft background and ring bands */}
          <circle cx={CX} cy={CY} r={RING.input + 40} fill="url(#hr-bg)" />
          {[RING.proj, RING.l1, RING.l2].map((r) => <circle key={r} cx={CX} cy={CY} r={r} className="hr__band" />)}

          {/* sparse curved links: each neuron to its nearest neurons on the next ring */}
          {inputs.map((i) => nearest(i.a, proj, 2).map((b) => (
            <path key={`ip-${i.f}-${i.t}-${b}`} d={link(RING.input, i.a, RING.proj, b)} stroke={COLORS[i.t]} className={`hr__link${active === i.t ? " is-on" : ""}${on(i.t)}`} />
          )))}
          {proj.map((x) => nearest(x, l1, 2).map((b) => <path key={`pl-${x}-${b}`} d={link(RING.proj, x, RING.l1, b)} stroke={INNER.proj} className="hr__link" />))}
          {l1.map((x) => nearest(x, l2, 2).map((b) => <path key={`ll-${x}-${b}`} d={link(RING.l1, x, RING.l2, b)} stroke={INNER.l1} className="hr__link" />))}
          {l2.map((x) => { const p = polar(RING.l2, x), q = polar(RING.emb + 2, x); return <line key={`le-${x}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke={INNER.l2} className="hr__link hr__link--in" />; })}

          {/* node-type arcs and labels */}
          {groups.map((g) => {
            const mid = (g.a0 + g.a1) / 2, p = polar(RING.input + 52 + 84 * Math.abs(Math.cos(rad(mid))), mid);
            return (
              <g key={g.t} className={`hr__grp${on(g.t)}`} {...hover(g.t)}>
                <path d={arc(RING.input + 17, g.a0 + 1.5, g.a1 - 1.5)} stroke={COLORS[g.t]} className="hr__typearc" />
                <text x={p.x} y={p.y} textAnchor="middle" className="hn__type" style={{ fill: COLORS[g.t] }}>{g.t} · {features[g.t].length}</text>
              </g>
            );
          })}

          {/* attention heads as soft arcs */}
          {[RING.l1, RING.l2].map((r, li) => Array.from({ length: h }, (_, k) => {
            const a0 = -90 + (360 / h) * k + 8, a1 = -90 + (360 / h) * (k + 1) - 8;
            const lp = polar(r + 15, -90 + (360 / h) * (k + 0.5));
            return (
              <g key={`${li}-${k}`}>
                <path d={arc(r + 11, a0, a1)} className={`hr__head hr__head--${k % 2}`} />
                {li === 0 && <text x={lp.x} y={lp.y + 3} textAnchor="middle" className="hr__headtext">head {k + 1}</text>}
              </g>
            );
          }))}

          {/* neurons */}
          {inputs.map((i) => {
            const p = polar(RING.input, i.a), lp = polar(RING.input + 28, i.a);
            const right = Math.cos(rad(i.a)) >= 0;
            return (
              <g key={`${i.t}-${i.f}`} className={`hr__grp${on(i.t)}${active === i.t ? " is-on" : ""}`} {...hover(i.t)}>
                <circle cx={p.x} cy={p.y} r={8.5} fill={COLORS[i.t]} className="hr__neuron" />
                <text x={lp.x} y={lp.y + 4} textAnchor={right ? "start" : "end"} className="hn__feat">{short(i.f)}</text>
              </g>
            );
          })}
          {proj.map((x) => { const p = polar(RING.proj, x); return <circle key={`p${x}`} cx={p.x} cy={p.y} r={litProj.has(x) ? 8 : 6.5} fill={litProj.has(x) ? (COLORS[active ?? ""] ?? INNER.proj) : INNER.proj} className="hr__neuron" />; })}
          {l1.map((x) => { const p = polar(RING.l1, x); return <circle key={`a${x}`} cx={p.x} cy={p.y} r={6.5} fill={INNER.l1} className="hr__neuron" />; })}
          {l2.map((x) => { const p = polar(RING.l2, x); return <circle key={`b${x}`} cx={p.x} cy={p.y} r={6} fill={INNER.l2} className="hr__neuron" />; })}

          {/* centre: channel embedding */}
          <circle cx={CX} cy={CY} r={RING.emb + 26} fill="url(#hr-glow)" />
          <circle cx={CX} cy={CY} r={RING.emb + 9} className="hr__halo" />
          <circle cx={CX} cy={CY} r={RING.emb} fill="url(#hr-core)" className="hr__core" />
          <text x={CX} y={CY - 1} textAnchor="middle" className="hr__coretext">{dims ?? "—"}-d</text>
          <text x={CX} y={CY + 13} textAnchor="middle" className="hr__coresub">embedding</text>

          {/* outputs */}
          <path d={`M${CX + RING.emb + 4},${CY - 10} C${CX + 300},${CY - 30} ${outA.x - 170},${outA.y} ${outA.x - 6},${outA.y}`} className="hr__out" />
          <path d={`M${CX + RING.emb + 4},${CY + 10} C${CX + 300},${CY + 30} ${outB.x - 170},${outB.y} ${outB.x - 6},${outB.y}`} className="hr__out hr__out--use" />
          {[{ o: outA, icon: "flow", title: "⟨u, v⟩ → σ", sub: "training: P(comment edge)", cls: "hr__card", col: "#475569" },
            { o: outB, icon: "bridges", title: "cos(A, B)", sub: "score: embedding component", cls: "hr__card hr__card--use", col: "#16a34a" }].map((c) => (
            <g key={c.title}>
              <rect x={c.o.x} y={c.o.y - 32} width={228} height={64} rx={14} className={c.cls} />
              <rect x={c.o.x + 14} y={c.o.y - 16} width={32} height={32} rx={16} fill={c.col} fillOpacity={0.1} />
              <g transform={`translate(${c.o.x + 21}, ${c.o.y - 9})`} style={{ color: c.col }} className="hr__cardicon"><Icon name={c.icon} size={18} /></g>
              <text x={c.o.x + 58} y={c.o.y - 3} className="hf__projtext">{c.title}</text>
              <text x={c.o.x + 58} y={c.o.y + 15} className="hf__small">{c.sub}</text>
            </g>
          ))}

          {/* ring key */}
          <g transform="translate(866, 500)">
            {[["#2563eb", `outer · ${total} input features`], [INNER.proj, `projection · ${hidden ?? "—"} units`],
              [INNER.l1, `HGT layer 1 · ${heads} heads · dropout ${dropout ?? "—"}`], [INNER.l2, `HGT layer ${Math.min(2, layers)} · ${heads} heads`],
              ["#0284c7", `centre · ${dims ?? "—"}-dim channel embedding`]].map(([c, t], i) => (
              <g key={t} transform={`translate(0, ${i * 21})`}>
                <circle cx={7} cy={-4} r={4.5} fill={c} />
                <text x={21} y={0} className="hf__small">{t}</text>
              </g>
            ))}
          </g>
        </svg>
      </div>
    </figure>
  );
}
