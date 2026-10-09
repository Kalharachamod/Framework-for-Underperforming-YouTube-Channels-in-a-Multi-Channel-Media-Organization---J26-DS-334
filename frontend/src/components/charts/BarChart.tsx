/**
 * Minimal, dependency-free charts. Bars use a FIXED domain passed by the caller (e.g. [0, 1] for
 * scores) so lengths are comparable and not exaggerated by auto-scaling. Each chart has a caption
 * and a text equivalent; the data tables on the page remain the primary accessible view.
 */

export interface Bar {
  key: string;
  label: string;
  value: number | null;
}

export function HorizontalBarChart({
  title,
  bars,
  min = 0,
  max = 1,
  unit,
  format = (v: number) => v.toFixed(3),
}: {
  title: string;
  bars: Bar[];
  min?: number;
  max?: number;
  unit: string;
  format?: (v: number) => string;
}) {
  const span = max - min || 1;
  const zero = ((Math.max(min, Math.min(0, max)) - min) / span) * 100;
  const summary = bars.map((b) => `${b.label}: ${b.value === null ? "not available" : format(b.value)}`).join("; ");
  return (
    <figure className="chart" aria-label={`${title}. ${summary}`}>
      <figcaption className="chart__caption">
        {title} <span className="muted">({unit}, axis {format(min)} to {format(max)})</span>
      </figcaption>
      <div className="chart__bars" aria-hidden="true">
        {bars.map((b) => {
          const v = b.value === null ? null : Math.max(min, Math.min(max, b.value));
          const pos = v === null ? zero : ((v - min) / span) * 100;
          const left = Math.min(zero, pos);
          const width = Math.abs(pos - zero);
          return (
            <div className="chart__row" key={b.key}>
              <span className="chart__label" title={b.label}>
                {b.label}
              </span>
              <span className="chart__track">
                {v !== null && <span className="chart__bar" style={{ left: `${left}%`, width: `${width}%` }} />}
                {min < 0 && <span className="chart__zero" style={{ left: `${zero}%` }} />}
              </span>
              <span className="chart__value">{b.value === null ? "n/a" : format(b.value)}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

/** Base score split into its diffusion and topic parts, on a fixed 0–1 axis. */
export function ComponentBar({ diffusion, topic }: { diffusion: number | null; topic: number | null }) {
  if (diffusion === null || topic === null) return <p className="muted">Score components not available for this pair.</p>;
  const d = Math.max(0, Math.min(1, diffusion)) * 100;
  const t = Math.max(0, Math.min(1 - d / 100, topic)) * 100;
  return (
    <figure
      className="chart"
      aria-label={`Base score ${(diffusion + topic).toFixed(3)}: diffusion ${diffusion.toFixed(3)} plus topic ${topic.toFixed(3)}, axis 0 to 1`}
    >
      <figcaption className="chart__caption">
        Base score composition <span className="muted">(axis 0 to 1)</span>
      </figcaption>
      <div className="stack" aria-hidden="true">
        <span className="stack__part stack__part--diffusion" style={{ width: `${d}%` }} />
        <span className="stack__part stack__part--topic" style={{ width: `${t}%` }} />
      </div>
      <p className="legend">
        <span className="legend__swatch legend__swatch--diffusion" aria-hidden="true" /> Diffusion {diffusion.toFixed(3)}
        <span className="legend__swatch legend__swatch--topic" aria-hidden="true" /> Topic {topic.toFixed(3)}
      </p>
    </figure>
  );
}
