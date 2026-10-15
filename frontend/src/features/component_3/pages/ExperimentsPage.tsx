import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num } from "../../../utils/format";
import { component3Api } from "../api";
import { useResearch } from "../ResearchContext";
import type { BridgeExperiment, CompareRun, Scalar } from "../types";

/** Recorded values as written: integers grouped, very small numbers in scientific notation (never rounded to 0). */
const scalar = (v: Scalar) => {
  if (v === null) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v !== "number") return v;
  if (Number.isInteger(v)) return int(v);
  return Math.abs(v) < 1e-3 ? v.toExponential(2) : String(Number(v.toPrecision(6)));
};

const day = (v: string | null | undefined) => (v ? date(v).slice(0, 10) : "—");
const weights = (x: { w_diffusion: number | null; w_embedding: number | null; w_topic: number | null }) =>
  `diffusion ${num(x.w_diffusion, 2)} · embedding ${num(x.w_embedding, 2)} · topic ${num(x.w_topic, 2)}`;
const signed = (v: number | null, d = 3) => (v === null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(d)}`);

function experimentStatus(e: BridgeExperiment): [Parameters<typeof Badge>[0]["tone"], string] {
  if (e.scored_pairs === null) return ["neutral", "recorded"];
  if (e.scored_pairs === 0) return ["warn", "no scored pairs"];
  return e.provisional ? ["warn", "provisional"] : ["ok", "complete"];
}

/** Results of one scoring experiment: its strongest stored pairs. */
function ExperimentResults({ experimentId }: { experimentId: string }) {
  const { snapshotId } = useResearch();
  const pairs = useApi((s) => component3Api.bridgePairs({ snapshotId, experimentId }, s), [snapshotId, experimentId]);
  if (pairs.status === "loading" || pairs.status === "idle") return <Loading variant="table" rows={3} label="Loading results…" />;
  if (pairs.status === "error") return <ErrorState error={pairs.error} onRetry={pairs.reload} what="Experiment results" />;
  const top = pairs.data.items.filter((r) => r.audience_bridge_score !== null).slice(0, 5);
  if (top.length === 0) return <p className="muted small">No scored pairs in this experiment.</p>;
  return (
    <ol className="xp-top">
      {top.map((r) => (
        <li key={`${r.source_channel_id}>${r.destination_channel_id}`}>
          <span>{r.source_channel_name} <span aria-label="to">→</span> {r.destination_channel_name}</span>
          <strong className="mono">{num(r.audience_bridge_score, 3)}</strong>
        </li>
      ))}
    </ol>
  );
}

function RunMeta({ title, run }: { title: string; run: CompareRun | null }) {
  return (
    <div className="cmp-run">
      <span>{title}</span>
      <strong className="mono">{run?.snapshot_id ?? "—"}</strong>
      {run && <small>{run.experiment_id ?? "no scoring run"} · {run.method_version ?? "—"} · {weights(run)}</small>}
    </div>
  );
}

/** Pair-level change between an older snapshot and the selected one. The backend decides compatibility. */
function SnapshotComparison({ current, options }: { current: string; options: { id: string; when: string | null }[] }) {
  const older = options.filter((o) => o.id !== current);
  const [base, setBase] = useState(older[0]?.id ?? "");
  const cmp = useApi((s) => component3Api.compare(base, current, s), [base, current], base !== "");
  if (older.length === 0) return <EmptyState title="Snapshot comparison unavailable for this selection."><p>Only one snapshot is stored.</p></EmptyState>;
  return (
    <>
      <div className="cmp-pick">
        <label><span>Previous snapshot</span>
          <select value={base} onChange={(e) => setBase(e.target.value)}>
            {older.map((o) => <option key={o.id} value={o.id}>{o.id}{o.when ? ` (${day(o.when)})` : ""}</option>)}
          </select>
        </label>
        <span className="cmp-pick__arrow" aria-hidden="true">→</span>
        <div className="cmp-pick__current"><span>Current snapshot</span><strong className="mono">{current}</strong></div>
      </div>
      {(cmp.status === "loading" || cmp.status === "idle") && <Loading variant="table" rows={5} label="Comparing snapshots…" />}
      {cmp.status === "error" && <ErrorState error={cmp.error} onRetry={cmp.reload} what="Snapshot comparison" />}
      {cmp.status === "success" && !cmp.data.compatible && (
        <EmptyState title="Snapshot comparison unavailable for this selection."><p>{cmp.data.reason}</p></EmptyState>
      )}
      {cmp.status === "success" && cmp.data.compatible && (
        <>
          <div className="cmp-runs">
            <RunMeta title="Previous" run={cmp.data.base} />
            <RunMeta title="Current" run={cmp.data.current} />
            <div className="cmp-run"><span>Configuration</span>
              <strong>{cmp.data.same_configuration ? "Same method version and weights" : "Different method version or weights"}</strong>
              <small>{cmp.data.same_configuration ? "Changes reflect the data, not the method." : "Changes mix data and method differences."}</small>
            </div>
          </div>
          <TableWrap label="Pair-level changes">
            <table className="table table--compact">
              <thead>
                <tr>
                  <th scope="col">Source → Destination</th>
                  <th scope="col" className="num">Score (prev → cur)</th>
                  <th scope="col" className="num">Score change</th>
                  <th scope="col" className="num">Rank change</th>
                  <th scope="col" className="num">Confidence change</th>
                  <th scope="col" className="num">Diffusion change</th>
                  <th scope="col" className="num">Topic sim. change</th>
                </tr>
              </thead>
              <tbody>
                {cmp.data.items.slice(0, 25).map((r) => (
                  <tr key={`${r.source_channel_id}>${r.destination_channel_id}`}>
                    <td>{r.source_channel_name ?? r.source_channel_id} <span aria-label="to">→</span> {r.destination_channel_name ?? r.destination_channel_id}</td>
                    <td className="num">{num(r.previous_score, 3)} → {num(r.current_score, 3)}</td>
                    <td className="num"><strong>{signed(r.score_change)}</strong></td>
                    <td className="num">{r.rank_change === null ? "—" : r.rank_change === 0 ? "0" : signed(-r.rank_change, 0)}</td>
                    <td className="num">{signed(r.confidence_change)}</td>
                    <td className="num">{signed(r.diffusion_change)}</td>
                    <td className="num">{signed(r.topic_similarity_change)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <p className="muted small">{int(cmp.data.items.length)} pairs, largest absolute score change first (top 25 shown). Rank change is positive when the destination moved up. {cmp.data.note}</p>
        </>
      )}
    </>
  );
}

export function ExperimentsPage() {
  const { snapshotId, status } = useResearch();
  const [params, setParams] = useSearchParams();
  const selected = params.get("experiment") ?? "";
  const selectedRun = params.get("run") ?? "";
  const experiments = useApi((s) => component3Api.experiments({ snapshotId }, s), [snapshotId]);
  const runs = useApi((s) => component3Api.researchRuns({ snapshotId }, s), [snapshotId]);
  const summary = useApi((s) => component3Api.dashboardSummary({ snapshotId }, s), [snapshotId]);
  const snapshots = useMemo(() => (status.status === "success" ? status.data.snapshots : []), [status]);
  const period = summary.status === "success" ? `${day(summary.data.first_video)} – ${day(summary.data.last_video)}` : "—";
  const items = experiments.status === "success" ? experiments.data.items : [];
  const exp = items.find((e) => e.experiment_id === selected) ?? null;
  const allRuns = runs.status === "success" ? runs.data.items : [];
  const run = allRuns.find((r) => r.run_id === selectedRun) ?? null;
  const linked = exp ? allRuns.filter((r) => r.run_id === exp.experiment_id || r.run_id === exp.embedding_experiment_id
    || exp.explanation_ids.includes(r.run_id) || exp.evaluation_ids.includes(r.run_id)) : [];
  const current = experiments.status === "success" ? experiments.data.snapshot_id : snapshotId ?? "";
  const currentMeta = snapshots.find((s) => s.snapshot_id === current);
  const currentWhen = currentMeta ? currentMeta.extracted_at ?? currentMeta.created_at : null;
  // only older snapshots can be the comparison base; newest first
  const olderSnapshots = snapshots
    .filter((s) => s.snapshot_id !== current && (!currentWhen || (s.extracted_at ?? s.created_at ?? "") < currentWhen))
    .reverse()
    // likely-compatible snapshots (same channel count) first; the backend still verifies compatibility
    .sort((a, b) => Number(b.channels === currentMeta?.channels) - Number(a.channels === currentMeta?.channels))
    .map((s) => ({ id: s.snapshot_id, when: s.extracted_at ?? s.created_at }));
  const select = (key: "experiment" | "run", v: string) => {
    const next = new URLSearchParams(params);
    next.set(key, v);
    setParams(next);
  };

  return (
    <>
      <PageHeader title="Experiments" description="Stored scoring experiments and research runs of the selected snapshot with their recorded configuration, artifacts and results, for reproducibility." />

      <Card title="Scoring experiments" info="Audience Bridge Score runs stored for this snapshot. Select one to inspect it.">
        {experiments.status === "loading" && <Loading variant="table" rows={3} label="Loading experiments…" />}
        {experiments.status === "error" && <ErrorState error={experiments.error} onRetry={experiments.reload} what="Scoring experiments" />}
        {experiments.status === "success" && (items.length === 0 ? <EmptyState title="No scoring experiment is stored for this snapshot." /> : (
          <TableWrap label="Scoring experiments">
            <table className="table table--compact table--select">
              <thead>
                <tr>
                  <th scope="col">Experiment</th><th scope="col">Snapshot</th><th scope="col">Created</th><th scope="col">Observation period</th>
                  <th scope="col" className="num">Channels</th><th scope="col">Methods (weights)</th><th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => {
                  const [tone, text] = experimentStatus(e);
                  return (
                    <tr key={e.experiment_id} className={e.experiment_id === selected ? "is-on" : ""}>
                      <td><button type="button" className="link-button" aria-pressed={e.experiment_id === selected} onClick={() => select("experiment", e.experiment_id)}><code>{e.experiment_id}</code></button></td>
                      <td className="mono small nowrap">{e.snapshot_id}</td>
                      <td>{date(e.created_at)}</td>
                      <td>{period}</td>
                      <td className="num">{runs.status === "success" ? int(runs.data.row_counts.channels) : "—"}</td>
                      <td className="small">{weights(e)}</td>
                      <td><Badge tone={tone}>{text}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableWrap>
        ))}
      </Card>

      {exp && (
        <section className="xp-detail" aria-label="Selected experiment">
          <Card title="Configuration">
            <KeyValues rows={[
              ["Experiment", <code key="e">{exp.experiment_id}</code>],
              ["Method version", `${exp.method_version ?? "—"}${exp.provisional ? " (provisional)" : ""}`],
              ["Weights", weights(exp)],
              ["Embedding source", exp.w_embedding > 0 ? exp.embedding_source : "not used"],
              ["Confidence k", scalar(exp.confidence_k)],
            ]} />
          </Card>
          <Card title="Artifacts">
            <KeyValues rows={[
              ["Embedding run", exp.embedding_experiment_id ? <code key="m">{exp.embedding_experiment_id}</code> : "—"],
              ["Explanations", exp.explanation_ids.length ? exp.explanation_ids.map((id) => <code key={id}>{id} </code>) : "none stored"],
              ["Linked research runs", int(linked.length)],
            ]} />
            {linked.length > 0 && (
              <ul className="xp-links">
                {linked.map((r) => <li key={r.run_id}><button type="button" className="link-button" onClick={() => select("run", r.run_id)}>{r.method}</button> <code className="small">{r.run_id}</code></li>)}
              </ul>
            )}
          </Card>
          <Card title="Evaluation">
            {exp.evaluation_ids.length === 0 ? <p className="muted small">No evaluation run uses this experiment.</p> : (
              <ul className="xp-links">
                {exp.evaluation_ids.map((id) => <li key={id}><Link to="/evaluation"><code>{id}</code></Link></li>)}
              </ul>
            )}
            <p className="muted small">Ground-truth relevance labels unavailable; evaluation compares rankings with baselines and across snapshots.</p>
          </Card>
          <Card title="Results">
            <KeyValues rows={[["Pairs", int(exp.pairs)], ["Scored pairs", int(exp.scored_pairs)]]} />
            <h3 className="sub-title">Strongest stored pairs</h3>
            <ExperimentResults experimentId={exp.experiment_id} />
          </Card>
        </section>
      )}

      <Card title="Snapshot comparison" info="Compares stored scores of the same directed pairs in two snapshots. Enabled only when both snapshots cover the same channel set and have a scoring run.">
        {status.status === "loading" ? <Loading variant="table" rows={3} /> : current ? (
          <SnapshotComparison key={current} current={current} options={olderSnapshots} />
        ) : <EmptyState title="Snapshot comparison unavailable for this selection." />}
      </Card>

      {runs.status === "loading" && <Loading variant="table" label="Loading runs…" />}
      {runs.status === "error" && <ErrorState error={runs.error} onRetry={runs.reload} what="Research runs" />}
      {runs.status === "success" && (
        <div className="rs-split">
          <Card title={`Research runs (${runs.data.items.length})`} info="Every stored pipeline run of this snapshot, newest first.">
            {runs.data.items.length === 0 ? <EmptyState title="No research data available for this snapshot." /> : (
              <TableWrap label="Research runs">
                <table className="table table--compact table--select">
                  <thead><tr><th scope="col">Run</th><th scope="col">Method</th><th scope="col">Created</th><th scope="col">Status</th></tr></thead>
                  <tbody>
                    {runs.data.items.map((r) => (
                      <tr key={r.run_id} className={r.run_id === selectedRun ? "is-on" : ""}>
                        <td><button type="button" className="link-button" aria-pressed={r.run_id === selectedRun} onClick={() => select("run", r.run_id)}><code>{r.run_id}</code></button></td>
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
      )}

      <Card title="Snapshots" info="Research snapshots are immutable.">
        {snapshots.length === 0 ? <EmptyState title="No research data available." /> : (
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
                    <td>{s.snapshot_id === current ? <Badge tone="ok">selected</Badge> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
        <p className="muted small">Switch snapshots and scoring experiments with the selectors in the top bar.</p>
      </Card>
    </>
  );
}
