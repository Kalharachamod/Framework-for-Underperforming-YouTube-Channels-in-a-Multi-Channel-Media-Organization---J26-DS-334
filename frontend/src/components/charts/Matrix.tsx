/**
 * Similarity heatmap and histogram. The heatmap is an HTML table (screen readers can read every value);
 * colour intensity is scaled over the observed value range, which the legend states explicitly.
 */
export interface MatrixAxis {
  id: string;
  label: string;
}

const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toFixed(2));

export function Heatmap({ axis, value, selected, onSelect, caption }: {
  axis: MatrixAxis[];
  value: (row: string, col: string) => number | null;
  selected?: string;
  onSelect?: (id: string) => void;
  caption: string;
}) {
  const vals = axis.flatMap((r) => axis.map((c) => (r.id === c.id ? null : value(r.id, c.id)))).filter((v): v is number => v !== null);
  const lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
  const shade = (v: number | null) => {
    if (v === null) return undefined;
    const t = hi > lo ? (v - lo) / (hi - lo) : 1;
    return `rgba(30, 58, 138, ${0.06 + 0.84 * t})`;
  };
  return (
    <div className="heat">
      <div className="heat__scroll">
        <table className="heat__table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              <th scope="col"><span className="sr-only">Channel</span></th>
              {axis.map((c, i) => (
                <th key={c.id} scope="col" title={c.label} className={selected === c.id ? "is-on" : ""}>
                  <button type="button" onClick={() => onSelect?.(c.id)} aria-label={`Highlight ${c.label}`}>{i + 1}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {axis.map((r, i) => (
              <tr key={r.id} className={selected === r.id ? "is-on" : ""}>
                <th scope="row">
                  <button type="button" onClick={() => onSelect?.(r.id)}><span className="heat__idx">{i + 1}</span>{r.label}</button>
                </th>
                {axis.map((c) => {
                  const v = r.id === c.id ? null : value(r.id, c.id);
                  const t = v !== null && hi > lo ? (v - lo) / (hi - lo) : 0;
                  const dim = selected !== undefined && selected !== r.id && selected !== c.id;
                  return (
                    <td key={c.id} title={r.id === c.id ? r.label : `${r.label} · ${c.label}: ${fmt(v)}`}
                      className={`${r.id === c.id ? "is-self" : ""}${dim ? " is-dim" : ""}${t > 0.55 ? " is-dark" : ""}`}
                      style={{ background: r.id === c.id ? undefined : shade(v) }}>
                      {r.id === c.id ? "—" : fmt(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="heat__legend">
        <span className="heat__ramp" aria-hidden="true" />
        Shading spans the observed range {fmt(lo)} – {fmt(hi)} (not 0–1), so small differences stay visible.
      </p>
    </div>
  );
}

export function Histogram({ bins, label }: { bins: { label: string; nodes: number }[]; label: string }) {
  const max = Math.max(1, ...bins.map((b) => b.nodes));
  return (
    <figure className="hist" aria-label={`${label}: ${bins.map((b) => `degree ${b.label}: ${b.nodes}`).join(", ")}`}>
      <div className="hist__bars" aria-hidden="true">
        {bins.map((b) => (
          <div key={b.label} className="hist__col" title={`degree ${b.label}: ${b.nodes.toLocaleString("en-US")} nodes`}>
            <span className="hist__n">{b.nodes ? b.nodes.toLocaleString("en-US") : ""}</span>
            <span className="hist__bar" style={{ height: `${(b.nodes / max) * 100}%` }} />
            <span className="hist__x">{b.label}</span>
          </div>
        ))}
      </div>
      <figcaption className="hist__caption">{label} · x: degree (observed edges) · y: nodes (linear)</figcaption>
    </figure>
  );
}
