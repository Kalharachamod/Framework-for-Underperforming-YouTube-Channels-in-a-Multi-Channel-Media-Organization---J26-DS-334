import { Select } from "../../components/common/ui";
import { date } from "../../utils/format";
import { useResearch } from "./ResearchContext";

export const LIMITATIONS =
  "Research estimates from a provisional scoring formula. A potential audience bridge is an audience-affinity " +
  "signal (structural connectivity and topic similarity); it does not show audience migration, subscriber " +
  "transfer, causal influence or future growth.";

/** Snapshot and experiment selectors (defaults: latest, as chosen by the API). */
export function ContextBar() {
  const { status, experiments, snapshotId, experimentId, setSnapshotId, setExperimentId } = useResearch();
  const snaps = status.status === "success" ? status.data.snapshots : [];
  const exps = experiments.status === "success" ? experiments.data.items : [];
  return (
    <div className="context-bar" role="group" aria-label="Research context">
      <Select
        id="ctx-snapshot"
        label="Snapshot"
        value={snapshotId ?? ""}
        onChange={(v) => setSnapshotId(v || null)}
        placeholder={snaps.length ? "Latest" : "No snapshots"}
        disabled={!snaps.length}
        options={[...snaps].reverse().map((s) => ({
          value: s.snapshot_id,
          label: `${s.snapshot_id} (${date(s.extracted_at ?? s.created_at)})`,
        }))}
      />
      <Select
        id="ctx-experiment"
        label="Scoring experiment"
        value={experimentId ?? ""}
        onChange={(v) => setExperimentId(v || null)}
        placeholder={exps.length ? "Latest" : "None available"}
        disabled={!exps.length}
        options={exps.map((e) => ({
          value: e.experiment_id,
          label: `${e.experiment_id} (w_d ${e.w_diffusion}, w_t ${e.w_topic}${e.provisional ? ", provisional" : ""})`,
        }))}
      />
    </div>
  );
}

/** The ids a response was computed from (always shown next to results). */
export function Provenance({ snapshotId, experimentId, extra }: { snapshotId?: string | null; experimentId?: string | null; extra?: string }) {
  return (
    <p className="provenance">
      Snapshot <code>{snapshotId ?? "—"}</code>
      {experimentId !== undefined && (
        <>
          {" · "}Experiment <code>{experimentId ?? "—"}</code>
        </>
      )}
      {extra && <> · {extra}</>}
    </p>
  );
}
