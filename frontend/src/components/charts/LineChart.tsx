/**
 * Dependency-free SVG charts built only from the values passed in. Axes start at 0 (no exaggerated
 * scales); every chart has a caption-level text alternative via aria-label.
 */
import { useEffect, useRef, useState } from "react";

/** Width of an element, kept up to date (charts draw at their real size so text never shrinks). */
function useWidth<T extends HTMLElement>(fallback: number): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export interface Series {
  key: string;
  label: string;
  color: string;
  values: (number | null)[];
}

const fmt = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(Math.round(v)));

/** Smooth path through the points (Catmull-Rom -> cubic Bezier); the curve passes exactly through every value. */
function smooth(pts: [number, number][], floor: number): string {
  if (pts.length === 0) return "";
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i += 1) {
    const p0 = pts[i - 1] ?? pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] ?? p2;
    const c1y = Math.min(floor, p1[1] + (p2[1] - p0[1]) / 6), c2y = Math.min(floor, p2[1] - (p3[1] - p1[1]) / 6);
    d += ` C${p1[0] + (p2[0] - p0[0]) / 6},${c1y} ${p2[0] - (p3[0] - p1[0]) / 6},${c2y} ${p2[0]},${p2[1]}`;
  }
  return d;
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p / 2) * 2 * p;
}

export function LineChart({ labels, series, height = 300, yLabel, summary }: {
  labels: string[];
  series: Series[];
  height?: number;
  yLabel: string;
  summary: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [box, width] = useWidth<HTMLElement>(760);
  const W = width, H = width < 520 ? Math.round(height * 0.8) : height, L = 46, R = 12, T = 12, B = 30;
  const every = Math.max(1, Math.ceil(labels.length / Math.max(2, Math.floor(W / 90))));
  const max = niceMax(Math.max(0, ...series.flatMap((s) => s.values.map((v) => v ?? 0))));
  const x = (i: number) => L + (labels.length <= 1 ? 0 : (i * (W - L - R)) / (labels.length - 1));
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  return (
    <figure className="linechart" aria-label={summary} ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-hidden="true" onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="linechart__grid" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" className="linechart__tick">{fmt(t)}</text>
          </g>
        ))}
        <text x={12} y={T + (H - T - B) / 2} transform={`rotate(-90 12 ${T + (H - T - B) / 2})`} textAnchor="middle" className="linechart__tick">{yLabel}</text>
        {labels.map((l, i) => (i % every === 0 || i === labels.length - 1) && ((labels.length - 1 - i >= every) || i === labels.length - 1) && (
          <text key={l} x={x(i)} y={H - 8} textAnchor={i === labels.length - 1 ? "end" : i === 0 ? "start" : "middle"} className="linechart__tick">{l}</text>
        ))}
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`lc-${s.key}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        {series.map((s) => {
          const pts = s.values.map((v, i) => [x(i), y(v ?? 0)] as [number, number]);
          const line = smooth(pts, y(0));
          return (
            <g key={s.key}>
              <path d={`${line} L${x(s.values.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill={`url(#lc-${s.key})`} />
              <path d={line} fill="none" stroke={s.color} strokeWidth={2.2} strokeLinejoin="round" />
            </g>
          );
        })}
        {labels.map((l, i) => (
          <rect key={`h${l}`} x={x(i) - (W - L - R) / Math.max(1, labels.length - 1) / 2} y={T} height={H - T - B}
            width={(W - L - R) / Math.max(1, labels.length - 1)} fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="linechart__cursor" />
            {series.map((s) => <circle key={s.key} cx={x(hover)} cy={y(s.values[hover] ?? 0)} r={3.5} fill={s.color} />)}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="linechart__tooltip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <strong>{labels[hover]}</strong>
          {series.map((s) => (
            <span key={s.key}><i style={{ background: s.color }} /> <span className="linechart__tip-name">{s.label}</span><b>{fmt(s.values[hover] ?? 0)}</b></span>
          ))}
        </div>
      )}
      <figcaption className="legend">
        {series.map((s) => (
          <span key={s.key} className="legend__item"><i style={{ background: s.color }} /> {s.label}</span>
        ))}
      </figcaption>
    </figure>
  );
}

export function Sparkline({ values, color, label }: { values: number[]; color: string; label: string }) {
  if (values.length < 2) return null;
  const W = 72, H = 30, max = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i * W) / (values.length - 1)},${H - 2 - (v / max) * (H - 4)}`).join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}
