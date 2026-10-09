import type { ReactNode } from "react";

export type Tone = "ok" | "warn" | "bad" | "neutral";

/** Status shown as text plus a symbol, so colour is never the only indicator. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  const symbol = { ok: "●", warn: "▲", bad: "■", neutral: "○" }[tone];
  return (
    <span className={`badge badge--${tone}`}>
      <span aria-hidden="true">{symbol}</span> {children}
    </span>
  );
}

export function Card({ title, actions, children }: { title?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card" aria-label={title}>
      {(title || actions) && (
        <header className="card__header">
          {title && <h2 className="card__title">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, description }: { title: string; description?: ReactNode }) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      {description && <p className="muted">{description}</p>}
    </header>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <aside className="notice" aria-label="Research limitations">
      {children}
    </aside>
  );
}

export function KeyValues({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v], i) => (
        <div className="kv__row" key={i}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Select({
  id,
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <nav className="pager" aria-label="Pagination">
      <button type="button" className="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Previous
      </button>
      <span>
        {from}–{to} of {total}
      </span>
      <button type="button" className="button" disabled={to >= total} onClick={() => onChange(offset + limit)}>
        Next
      </button>
    </nav>
  );
}

/** Wrapper that lets wide tables scroll horizontally instead of breaking the layout. */
export function TableWrap({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
