import type { ReactNode } from "react";
import type { ApiError } from "../../services/apiClient";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="state state--loading" role="status" aria-live="polite">
      {label}
    </p>
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
};

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const unavailable = error.code === "artifact_unavailable" || error.code === "not_found";
  return (
    <div className={`state ${unavailable ? "state--empty" : "state--error"}`} role="alert">
      <p className="state__title">{unavailable ? "Not available" : "Could not load data"}</p>
      <p>{error.message}</p>
      {HINTS[error.code] && <p className="muted">{HINTS[error.code]}</p>}
      {onRetry && !unavailable && (
        <button type="button" className="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
