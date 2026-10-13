/**
 * Decomposition of one stored Audience Bridge Score: the weighted components add up to the base score,
 * which is multiplied by the confidence. Values are displayed as received; nothing is recalculated.
 */
import { InfoTip } from "../common/InfoTip";

export interface Breakdown {
  diffusion: number | null;
  embedding: number | null;
  topic: number | null;
  base: number | null;
  confidence: number | null;
  score: number | null;
  embeddingUsed?: boolean;
}

const fmt = (v: number | null) => (v === null ? "—" : v.toFixed(3));

function Row({ label, value, tone, hint }: { label: string; value: number | null; tone: string; hint?: string }) {
  return (
    <div className="sbd__row">
      <span className="sbd__label">{label}{hint && <small>{hint}</small>}</span>
      <span className="sbd__track" aria-hidden="true">
        <span className={`sbd__bar sbd__bar--${tone}`} style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
      </span>
      <span className="sbd__value">{fmt(value)}</span>
    </div>
  );
}

export function ScoreBreakdown({ b, compact = false }: { b: Breakdown; compact?: boolean }) {
  return (
    <figure className={`sbd${compact ? " sbd--compact" : ""}`}
      aria-label={`Audience Bridge Score ${fmt(b.score)} = base score ${fmt(b.base)} × confidence ${fmt(b.confidence)}; base = diffusion ${fmt(b.diffusion)} + embedding ${fmt(b.embedding)} + topic ${fmt(b.topic)}`}>
      <div className="sbd__head">
        <span className="sbd__title">Score decomposition</span>
        <InfoTip label="About the formula">
          AudienceBridgeScore = BaseScore × Confidence. BaseScore = diffusion + embedding + topic components (each is
          its weight × the normalised signal). Confidence = shared-commenter evidence × topic coverage. Axis 0–1.
        </InfoTip>
      </div>
      <Row label="Diffusion" hint="Personalized PageRank" value={b.diffusion} tone="diffusion" />
      {b.embeddingUsed !== false && <Row label="Embedding" hint="graph representation" value={b.embedding} tone="embedding" />}
      <Row label="Topic" hint="semantic similarity" value={b.topic} tone="topic" />
      <div className="sbd__rule" />
      <Row label="Base score" value={b.base} tone="base" />
      <Row label="× Confidence" value={b.confidence} tone="confidence" />
      <div className="sbd__final">
        <span>Audience Bridge Score</span>
        <strong>{fmt(b.score)}</strong>
      </div>
    </figure>
  );
}
