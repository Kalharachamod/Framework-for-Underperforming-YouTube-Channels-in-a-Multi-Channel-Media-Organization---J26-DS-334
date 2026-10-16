import type { ReactNode } from "react";

/** Collapsed-by-default section: a summary row (title, hint, count badge) that expands in place. */
export function Fold({ title, hint, badge, children, open = false }: {
  title: string; hint?: string; badge?: ReactNode; children: ReactNode; open?: boolean;
}) {
  return (
    <details className="xblock runs-fold" aria-label={title} open={open}>
      <summary>
        <span className="runs-fold__title"><b>{title}</b>{hint && <small>{hint}</small>}</span>
        {badge !== undefined && <span className="runs-fold__count">{badge}</span>}
        <span className="runs-fold__chev" aria-hidden="true" />
      </summary>
      <div className="runs-fold__body">{children}</div>
    </details>
  );
}
