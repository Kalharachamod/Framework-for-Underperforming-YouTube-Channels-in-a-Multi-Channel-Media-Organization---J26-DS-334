/** Quick-analysis snapshots skip HGT, node2vec and the evaluation for speed. This explains that, instead of
 * a bare "not run", and offers to complete the analysis (runs only the skipped stages). */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, describeError } from "../../services/apiClient";
import { analysisApi } from "./analysisApi";
import { useResearch } from "./ResearchContext";

/** The selected snapshot (latest when none is chosen) and whether it comes from a quick analysis. */
export function useQuickSnapshot(): { quick: boolean; organization: string | null; snapshotId: string | null } {
  const { status, snapshotId } = useResearch();
  if (status.status !== "success") return { quick: false, organization: null, snapshotId };
  const sid = snapshotId ?? status.data.latest_snapshot_id;
  const meta = status.data.snapshots.find((s) => s.snapshot_id === sid);
  return { quick: Boolean(meta?.quick_analysis), organization: meta?.organization ?? null, snapshotId: sid ?? null };
}

export function CompleteAnalysisButton({ snapshotId, label = "Complete analysis" }: { snapshotId: string; label?: string }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const job = await analysisApi.complete(snapshotId);
      navigate(`/analyze?job=${encodeURIComponent(job.job_id)}`);
    } catch (err) {
      setError(err instanceof ApiError && err.code === "conflict"
        ? "Another analysis is already running. Try again when it has finished." : describeError(err));
      setBusy(false);
    }
  };
  return (
    <span className="qa-action">
      <button type="button" className="button button--primary" onClick={run} disabled={busy}>{busy ? "Starting…" : label}</button>
      {error && <span className="az-error" role="alert">{error}</span>}
    </span>
  );
}

/** Shown in place of an empty state when the missing result was skipped by a quick analysis. */
export function QuickSkipNotice({ what, fallback }: { what: string; fallback: React.ReactNode }) {
  const { quick, organization, snapshotId } = useQuickSnapshot();
  if (!quick || !snapshotId) return <>{fallback}</>;
  return (
    <div className="qa-notice" role="note">
      <div>
        <strong>{what} was skipped in the quick analysis</strong>
        <p>
          The quick analysis of {organization ?? "this organization"} stops at the Audience Bridge Score to stay fast.
          Completing it adds HGT, the node2vec baseline and an evaluation (agreement, top-k and, when an earlier
          snapshot of the same organization exists, temporal stability). It usually takes a few minutes.
        </p>
      </div>
      <CompleteAnalysisButton snapshotId={snapshotId} />
    </div>
  );
}
