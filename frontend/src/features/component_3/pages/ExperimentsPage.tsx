import { useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label } from "../../../utils/format";
import { component3Api } from "../api";
import { useResearch } from "../ResearchContext";
import type { Scalar } from "../types";

/** Recorded values as written: integers grouped, very small numbers in scientific notation (never rounded to 0). */
const scalar = (v: Scalar) => {
  if (v === null) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v !== "number") return v;
  if (Number.isInteger(v)) return int(v);
  return Math.abs(v) < 1e-3 ? v.toExponential(2) : String(Number(v.toPrecision(6)));
};

export function ExperimentsPage() {
  const { snapshotId, status } = useResearch();
  const [params, setParams] = useSearchParams();
  const selected = params.get("run") ?? "";
  const runs = useApi((s) => component3Api.researchRuns({ snapshotId }, s), [snapshotId]);
  const summary = useApi((s) => component3Api.dashboardSummary({ snapshotId }, s), [snapshotId]);
  const run = runs.status === "success" ? runs.data.items.find((r) => r.run_id === selected) ?? null : null;
  const snapshots = status.status === "success" ? status.data.snapshots : [];

  return (
    <>
      <PageHeader title="Experiments" description="Every stored research run of the selected snapshot with its recorded configuration and validation result, for reproducibility." />
      {runs.status === "loading" && <Loading label="Loading runs…" />}
      {runs.status === "error" && <ErrorState error={runs.error} onRetry={runs.reload} />}
      {runs.status === "success" && (
        <>
          <section className="rs-strip" aria-label="Snapshot">
            <div className="rs-strip__cell"><span>Snapshot</span><strong className="rs-strip__text">{runs.data.snapshot_id}</strong><small>extracted {date(runs.data.snapshot_extracted_at ?? runs.data.snapshot_created_at)}</small></div>
            <div className="rs-strip__cell"><span>Channels</span><strong>{int(runs.data.row_counts.channels)}</strong></div>
            <div className="rs-strip__cell"><span>Videos</span><strong>{int(runs.data.row_counts.videos)}</strong></div>
            <div className="rs-strip__cell"><span>Comments</span><strong>{int(runs.data.row_counts.comments)}</strong></div>
            <div className="rs-strip__cell"><span>Observation period</span><strong className="rs-strip__text">
              {summary.status === "success" ? `${date(summary.data.first_video).slice(0, 10)} – ${date(summary.data.last_video).slice(0, 10)}` : "—"}
            </strong><small>video publish dates</small></div>
          </section>
          <div className="rs-split">
            <Card title={`Research runs (${runs.data.items.length})`} info="Newest first. Select a run to inspect its configuration.">
              {runs.data.items.length === 0 ? <EmptyState title="No research data available for this snapshot." /> : (
                <TableWrap label="Research runs">
                  <table className="table table--compact table--select">
                    <thead><tr><th scope="col">Run</th><th scope="col">Method</th><th scope="col">Created</th><th scope="col">Status</th></tr></thead>
                    <tbody>
                      {runs.data.items.map((r) => (
                        <tr key={r.run_id} className={r.run_id === selected ? "is-on" : ""}>
                          <td><button type="button" className="link-button" aria-pressed={r.run_id === selected} onClick={() => setParams({ run: r.run_id })}><code>{r.run_id}</code></button></td>
                          <td>{r.method}<small className="run-step">{r.step}</small></td>
                          <td>{date(r.created_at)}</td>
                          <td>{r.validation_passed === null ? <Badge tone="neutral">recorded</Badge> : r.validation_passed ? <Badge tone="ok">validated</Badge> : <Badge tone="bad">failed</Badge>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
              )}
            </Card>
            <Card title={run ? `${run.method} · ${run.run_id}` : "Run configuration"}>
              {!run ? <EmptyState title="Select a run to see its recorded configuration." /> : (
                <>
                  <KeyValues rows={[
                    ["Run id", <code key="i">{run.run_id}</code>],
                    ["Method", run.method],
                    ["Pipeline step", run.step],
                    ["Artifact folder", <code key="k">{run.kind}</code>],
                    ["Created", date(run.created_at)],
                    ["Validation", run.validation_passed === null ? "not recorded by this step" : run.validation_passed ? "passed" : "failed"],
                  ]} />
                  <h3 className="sub-title">Configuration</h3>
                  {Object.keys(run.config).length === 0 ? <p className="muted">No configuration recorded in the run metadata.</p> : (
                    <KeyValues rows={Object.entries(run.config).map(([k, v]) => [label(k), scalar(v)] as [string, string])} />
                  )}
                </>
              )}
            </Card>
          </div>
          <Card title="Snapshots" info="Research snapshots are immutable. Snapshots are compared only inside the evaluation (temporal stability), where the backend pairs a snapshot with the latest earlier snapshot of the same channel set.">
            <TableWrap label="Snapshots">
              <table className="table table--compact">
                <thead><tr><th scope="col">Snapshot</th><th scope="col">Extracted</th><th scope="col" className="num">Channels</th><th scope="col" className="num">Videos</th><th scope="col" className="num">Comments</th><th scope="col">In view</th></tr></thead>
                <tbody>
                  {[...snapshots].reverse().map((s) => (
                    <tr key={s.snapshot_id}>
                      <td><code>{s.snapshot_id}</code></td>
                      <td>{date(s.extracted_at ?? s.created_at)}</td>
                      <td className="num">{int(s.channels)}</td>
                      <td className="num">{int(s.videos)}</td>
                      <td className="num">{int(s.comments)}</td>
                      <td>{s.snapshot_id === runs.data.snapshot_id ? <Badge tone="ok">selected</Badge> : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <p className="muted small">Switch snapshots and scoring experiments with the selectors in the top bar.</p>
          </Card>
        </>
      )}
    </>
  );
}
