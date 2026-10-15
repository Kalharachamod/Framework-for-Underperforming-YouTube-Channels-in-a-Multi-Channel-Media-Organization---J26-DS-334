import { pct } from "../../utils/format";

/** Semicircle gauge for a 0–1 share. */
export function Gauge({ value, label, caption }: { value: number | null; label: string; caption: string }) {
  const v = Math.max(0, Math.min(1, value ?? 0)), r = 46, c = Math.PI * r;
  return (
    <figure className="gauge" aria-label={`${label}: ${pct(value, 0)}`}>
      <svg viewBox="0 0 120 70" aria-hidden="true">
        <path d="M14 62 A46 46 0 0 1 106 62" className="gauge__track" />
        <path d="M14 62 A46 46 0 0 1 106 62" className="gauge__value" strokeDasharray={`${c * v} ${c}`} />
        <text x="60" y="58" textAnchor="middle" className="gauge__num">{value === null ? "—" : pct(value, 0)}</text>
      </svg>
      <figcaption><strong>{label}</strong><span>{caption}</span></figcaption>
    </figure>
  );
}

