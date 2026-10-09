import { useEffect, useMemo, useState } from "react";
import { HorizontalBarChart } from "../../../components/charts/BarChart";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, Notice, PageHeader, Select, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, label, num, scalar } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { channelName, useResearch } from "../ResearchContext";
import type { Scalar } from "../types";

type Row = Record<string, Scalar>;

const METRIC_HELP: Record<string, string> = {
  spearman: "Spearman rank correlation between two methods' rankings of the same destinations (−1 to 1).",
  kendall: "Kendall tau-b rank correlation (−1 to 1), robust to ties.",
  topk_jaccard: "Overlap of the two top-k destination lists: |A ∩ B| / |A ∪ B| (0 to 1).",
  precision_at_k: "Share of the top-k destinations that are labelled relevant.",
  recall_at_k: "Share of labelled-relevant destinations found in the top k.",
  ndcg_at_k: "Ranking quality against graded relevance labels (0 to 1).",
  mrr: "1 / rank of the first relevant destination, averaged over sources.",
  topk_distinct_destinations: "How many different destinations appear across all sources' top-k lists (low = a few hubs dominate).",
  topk_boundary_tie_share: "Share of sources whose k-th and (k+1)-th scores tie (top-k depends on tie-breaking).",
  score_coverage: "Share of full-data scored pairs still scored under sparser data.",
};

function Metric({ name }: { name: string }) {
  return <abbr title={METRIC_HELP[name] ?? name}>{label(name)}</abbr>;
}

function RowsTable({ rows, columns, caption }: { rows: Row[]; columns: string[]; caption: string }) {
  return (
    <TableWrap label={caption}>
      <table className="table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>{columns.map((c) => <th scope="col" key={c}>{label(c)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} className={typeof r[c] === "number" ? "num" : undefined}>
                  {c === "metric" && typeof r[c] === "string" ? <Metric name={r[c] as string} /> : scalar(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export function EvaluationPage() {
  const { snapshotId, channels } = useResearch();
  const runs = useApi((s) => component3Api.evaluationRuns({ snapshotId }, s), [snapshotId]);
  const [selected, setSelected] = useState("");
  useEffect(() => setSelected(""), [snapshotId]);
  const evaluationId = selected || (runs.status === "success" ? runs.data.items[0]?.evaluation_id ?? "" : "");
  const enabled = evaluationId !== "";
  const c = { snapshotId };
  const meta = useApi((s) => component3Api.evaluationMetadata(evaluationId, c, s), [evaluationId, snapshotId], enabled);
  const ranking = useApi((s) => component3Api.evaluationAllRows(evaluationId, "ranking", c, {}, s), [evaluationId, snapshotId], enabled);
  const temporal = useApi((s) => component3Api.evaluationAllRows(evaluationId, "temporal_stability", c, {}, s), [evaluationId, snapshotId], enabled);
  const sparse = useApi((s) => component3Api.evaluationAllRows(evaluationId, "sparse_robustness", c, {}, s), [evaluationId, snapshotId], enabled);
  const perf = useApi((s) => component3Api.evaluationAllRows(evaluationId, "performance", c, {}, s), [evaluationId, snapshotId], enabled);
  const [topkMethod, setTopkMethod] = useState("audience_bridge_score");
  const topk = useApi((s) => component3Api.evaluationRows(evaluationId, "top_k", c, { method: topkMethod, limit: 100 }, s), [evaluationId, snapshotId, topkMethod], enabled);

  const rows = ranking.status === "success" ? (ranking.data.items as Row[]) : [];
  const relevance = rows.filter((r) => r.analysis === "relevance");
  const statusRows = rows.filter((r) => r.analysis === "method_status");
  const agreement = useMemo(() => {
    const map = new Map<string, Record<string, Scalar>>();
    for (const r of rows.filter((x) => x.analysis === "agreement")) {
      const key = `${r.method}|${r.reference_method}`;
      const entry = map.get(key) ?? { method: r.method, reference_method: r.reference_method };
      const col = r.k === null ? String(r.metric) : `${r.metric}@${r.k}`;
      entry[col] = r.value;
      entry[`${col}_n`] = r.n_sources;
      map.set(key, entry);
    }
    return [...map.values()];
  }, [rows]);
  const agreementCols = useMemo(() => {
    const cols = new Set<string>();
    agreement.forEach((a) => Object.keys(a).forEach((k) => !k.endsWith("_n") && k !== "method" && k !== "reference_method" && cols.add(k)));
    return [...cols].sort();
  }, [agreement]);
  const proposedVs = agreement.filter((a) => a.method === "audience_bridge_score" || a.reference_method === "audience_bridge_score");

  if (runs.status === "loading" || runs.status === "idle") return <Loading label="Loading evaluation runs…" />;
  if (runs.status === "error") return <ErrorState error={runs.error} onRetry={runs.reload} />;

  return (
    <>
      <PageHeader title="Evaluation" description="Stored STEP 21 results comparing the proposed Audience Bridge Score with its components and the Louvain and node2vec baselines." />
      <Notice>
        Without relevance labels, these results measure <strong>consistency</strong> between methods (agreement, stability, robustness), not correctness. Agreement with a baseline does not prove either method is right.
      </Notice>
      {runs.data.items.length === 0 ? (
        <EmptyState title="No evaluation has been run for this snapshot">
          <p>Run python -m research.component_3.evaluation.evaluate to produce evaluation results.</p>
        </EmptyState>
      ) : (
        <>
          <Card>
            <Select id="eval-run" label="Evaluation run" value={evaluationId} onChange={setSelected}
              options={runs.data.items.map((r) => ({ value: r.evaluation_id, label: `${r.evaluation_id} (${date(r.created_at)})` }))} />
          </Card>

          {meta.status === "loading" && <Loading />}
          {meta.status === "error" && <ErrorState error={meta.error} onRetry={meta.reload} />}
          {meta.status === "success" && (
            <div className="grid grid--2">
              <Card title="Methods">
                <TableWrap label="Methods">
                  <table className="table">
                    <thead><tr><th scope="col">Method</th><th scope="col">Role</th><th scope="col">Status</th></tr></thead>
                    <tbody>
                      {Object.entries(meta.data.methods).map(([m, v]) => (
                        <tr key={m}>
                          <td>{label(m)}</td>
                          <td>{scalar(v.role)}</td>
                          <td><Badge tone={v.status === "ok" ? "ok" : "warn"}>{scalar(v.status)}</Badge>{v.reason ? <span className="muted"> {scalar(v.reason)}</span> : null}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
              </Card>
              <Card title="Run">
                <KeyValues rows={[
                  ["Relevance labels", scalar(meta.data.labels.status ?? "supplied")],
                  ["Temporal stability", `${scalar(meta.data.temporal.status)}${meta.data.temporal.reason ? ` (${scalar(meta.data.temporal.reason)})` : ""}`],
                  ["Sparse-data simulations", `${scalar(meta.data.sparse_robustness.runs ?? 0)} runs`],
                  ["As of", date(meta.data.as_of as string | null)],
                  ["Created", date(meta.data.created_at)],
                ]} />
                {meta.data.interpretation && <p className="muted">{meta.data.interpretation}</p>}
              </Card>
            </div>
          )}

          <Card title="Ranking quality (relevance metrics)">
            {ranking.status === "loading" && <Loading />}
            {ranking.status === "error" && <ErrorState error={ranking.error} />}
            {ranking.status === "success" && (relevance.every((r) => r.status === "not_computed") ? (
              <p><Badge tone="neutral">Not computed</Badge> No explicit relevance labels were supplied, so Precision@k, Recall@k, NDCG@k and MRR are not available.</p>
            ) : (
              <RowsTable caption="Relevance metrics" rows={relevance} columns={["method", "metric", "k", "value", "n_sources", "status"]} />
            ))}
            {statusRows.length > 0 && <RowsTable caption="Unavailable methods" rows={statusRows} columns={["method", "status", "reason"]} />}
          </Card>

          <Card title="Ranking consistency between methods">
            {ranking.status === "success" && agreement.length === 0 && <p className="muted">No agreement results in this run.</p>}
            {proposedVs.length > 0 && (
              <HorizontalBarChart
                title="Spearman agreement of the Audience Bridge Score with each method"
                unit="correlation" min={-1} max={1}
                bars={proposedVs.map((a) => {
                  const other = a.method === "audience_bridge_score" ? a.reference_method : a.method;
                  return { key: String(other), label: label(String(other)), value: typeof a.spearman === "number" ? a.spearman : null };
                })}
              />
            )}
            {agreement.length > 0 && (
              <TableWrap label="Agreement">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Method</th><th scope="col">Compared with</th>
                      {agreementCols.map((c2) => <th scope="col" key={c2}><Metric name={c2.split("@")[0]} />{c2.includes("@") ? `@${c2.split("@")[1]}` : ""}</th>)}
                      <th scope="col">Sources</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agreement.map((a) => (
                      <tr key={`${a.method}|${a.reference_method}`}>
                        <td>{label(String(a.method))}</td><td>{label(String(a.reference_method))}</td>
                        {agreementCols.map((c2) => <td className="num" key={c2}>{num(a[c2] as number | null)}</td>)}
                        <td className="num">{scalar(a.spearman_n ?? null)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </Card>

          <Card title="Top-k results">
            <RowsTable caption="Top-k summary" rows={rows.filter((r) => r.analysis === "top_k_summary")} columns={["method", "metric", "k", "value", "n_sources", "status"]} />
            <Select id="topk-method" label="Top-k lists for method" value={topkMethod} onChange={setTopkMethod}
              options={(meta.status === "success" ? Object.keys(meta.data.methods) : [topkMethod]).map((m) => ({ value: m, label: label(m) }))} />
            {topk.status === "loading" && <Loading />}
            {topk.status === "error" && <ErrorState error={topk.error} />}
            {topk.status === "success" && (topk.data.items.length === 0 ? <p className="muted">No top-k rows for this method.</p> : (
              <>
                <RowsTable caption="Top-k destinations" columns={["source", "rank", "destination", "score", "tied"]}
                  rows={topk.data.items.map((r) => ({ ...r, source: channelName(channels.status === "success" ? channels.data.items : [], r.source_channel_id as string), destination: channelName(channels.status === "success" ? channels.data.items : [], r.destination_channel_id as string) }))} />
                {topk.data.total > topk.data.items.length && <p className="muted">Showing the first {topk.data.items.length} of {topk.data.total} rows.</p>}
              </>
            ))}
          </Card>

          <Card title="Temporal stability">
            {temporal.status === "loading" && <Loading />}
            {temporal.status === "error" && <ErrorState error={temporal.error} />}
            {temporal.status === "success" && (temporal.data.items.length === 0 ? <p className="muted">Temporal stability was not run.</p> :
              temporal.data.items.every((r) => r.status === "insufficient_temporal_data" || r.status === "not_comparable") ? (
                <p><Badge tone="neutral">Insufficient temporal data</Badge> {scalar(temporal.data.items.find((r) => r.reason)?.reason ?? null)}</p>
              ) : (
                <RowsTable caption="Temporal stability" rows={temporal.data.items.filter((r) => r.status === "ok")} columns={["method", "earlier_snapshot_id", "later_snapshot_id", "metric", "k", "value", "n_sources"]} />
              ))}
          </Card>

          <Card title="Sparse-data robustness">
            {sparse.status === "loading" && <Loading />}
            {sparse.status === "error" && <ErrorState error={sparse.error} />}
            {sparse.status === "success" && (sparse.data.items.length === 0 ? (
              <p><Badge tone="neutral">Not run</Badge> This evaluation was run without sparse-data simulations.</p>
            ) : (
              <RowsTable caption="Sparse-data robustness" rows={sparse.data.items} columns={["method", "unit", "retain_fraction", "seed", "metric", "k", "value", "n_sources", "status"]} />
            ))}
          </Card>

          <Card title="Computational performance">
            {perf.status === "loading" && <Loading />}
            {perf.status === "error" && <ErrorState error={perf.error} />}
            {perf.status === "success" && (
              <>
                <RowsTable caption="Measured performance" rows={perf.data.items} columns={["stage", "method", "status", "seconds", "python_heap_peak_mib", "graph_nodes", "graph_edges"]} />
                {meta.status === "success" && <p className="muted">{scalar(meta.data.performance.memory_note ?? null)}</p>}
              </>
            )}
          </Card>
          <Provenance snapshotId={runs.data.snapshot_id} extra={`Evaluation ${evaluationId}`} />
        </>
      )}
    </>
  );
}
