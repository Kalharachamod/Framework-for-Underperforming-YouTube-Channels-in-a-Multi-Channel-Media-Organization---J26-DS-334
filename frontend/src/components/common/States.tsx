import type { ReactNode } from "react";
import type { ApiError } from "../../services/apiClient";

export type SkeletonKind = "block" | "graph" | "table" | "cards" | "chart";

/** Loading placeholder shaped like the content it replaces (graph, table rows, metric cards, chart).
 * Screen readers hear the label; sighted users see the skeleton, never a blank area. */
export function Loading({ label = "Loading…", variant = "block", rows = 5 }: { label?: string; variant?: SkeletonKind; rows?: number }) {
  return (
    <div className={`skel skel--${variant}`} role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {variant === "graph" && (
        <div className="skel__graph" aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => <span key={i} className="skel__node" style={{ left: `${12 + ((i * 37) % 76)}%`, top: `${14 + ((i * 53) % 70)}%` }} />)}
          <span className="skel__caption">{label}</span>
        </div>
      )}
      {variant === "table" && (
        <div className="skel__table" aria-hidden="true">
          <span className="skel__row skel__row--head" />
          {Array.from({ length: rows }, (_, i) => <span key={i} className="skel__row" />)}
        </div>
      )}
      {variant === "cards" && (
        <div className="skel__cards" aria-hidden="true">{Array.from({ length: rows }, (_, i) => <span key={i} className="skel__card" />)}</div>
      )}
      {variant === "chart" && <div className="skel__chart" aria-hidden="true"><span /></div>}
      {variant === "block" && (
        <div className="skel__block" aria-hidden="true">
          <span className="skel__line" style={{ width: "42%" }} />
          <span className="skel__line" style={{ width: "88%" }} />
          <span className="skel__line" style={{ width: "70%" }} />
        </div>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state--empty" role="status">
      <p className="state__title">{title}</p>
      {children && <div className="state__body">{children}</div>}
    </div>
  );
}

const HINTS: Partial<Record<string, string>> = {
  network_error: "Start the backend (uvicorn backend.main:app) and check VITE_API_URL.",
  artifact_unavailable: "This research artifact has not been produced yet. Run the corresponding pipeline step.",
  storage_unavailable: "Stored research artifacts could not be read.",
  rate_limited: "Wait a moment, then retry.",
  timeout: "The request took too long; retrying usually helps.",
};

/** Error panel: what failed (`what`), the reason, and a retry button only when retrying can help. */
export function ErrorState({ error, onRetry, what }: { error: ApiError; onRetry?: () => void; what?: string }) {
  const unavailable = error.code === "artifact_unavailable" || error.code === "not_found";
  const title = unavailable ? (what ? `${what}: not available` : "Not available") : what ? `${what} could not be loaded` : "Could not load data";
  return (
    <div className={`state ${unavailable ? "state--empty" : "state--error"}`} role="alert">
      <p className="state__title">{title}</p>
      <p>{error.message}</p>
      {HINTS[error.code] && <p className="muted">{HINTS[error.code]}</p>}
      {onRetry && !unavailable && error.retryable !== false && (
        <button type="button" className="button" onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}
