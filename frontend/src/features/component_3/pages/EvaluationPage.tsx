import { useEffect, useMemo, useState } from "react";
import { HorizontalBarChart } from "../../../components/charts/BarChart";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Icon } from "../../../components/common/Icon";
import { Badge, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num, scalar } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { QuickSkipNotice } from "../QuickAnalysis";
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

/** Conventional reading of an agreement value. Agreement measures consistency between rankings, not correctness. */
function interpret(metric: string, v: number | null): string {
  if (v === null) return "Not computed";
  const base = metric.split("@")[0];
  if (base === "spearman" || base === "kendall") {
    const a = Math.abs(v);
    const strength = a >= 0.7 ? "strong" : a >= 0.4 ? "moderate" : a >= 0.2 ? "weak" : "negligible";
    return `${strength[0].toUpperCase()}${strength.slice(1)} ${v >= 0 ? "agreement" : "inverse agreement"} between rankings`;
  }
  if (base === "topk_jaccard") return v >= 0.5 ? "High overlap of top-k lists" : v >= 0.25 ? "Partial overlap of top-k lists" : "Low overlap of top-k lists";
  return "See metric definition";
}

const METHOD_GROUPS: { title: string; kind: string; method: string; note: string }[] = [
  { title: "Proposed framework", kind: "Audience Bridge Score", method: "audience_bridge_score", note: "Diffusion, graph representation and topic similarity, confidence weighted." },
  { title: "Structural baseline", kind: "Louvain", method: "louvain", note: "Community structure of the channel overlap graph." },
  { title: "Representation baseline", kind: "node2vec", method: "node2vec", note: "Homogeneous random-walk embeddings, channel similarity." },
];

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

  if (runs.status === "loading" || runs.status === "idle") return <Loading variant="cards" label="Loading evaluation runs…" />;
  if (runs.status === "error") return <ErrorState error={runs.error} onRetry={runs.reload} what="Evaluation runs" />;

  const vsOf = (method: string) => agreement.find((a) => (a.method === "audience_bridge_score" && a.reference_method === method) || (a.reference_method === "audience_bridge_score" && a.method === method));
  const spear = (method: string) => { const v = vsOf(method)?.spearman; return typeof v === "number" ? v : null; };
  const tone = (v: number | null) => (v === null ? "none" : Math.abs(v) >= 0.7 ? "strong" : Math.abs(v) >= 0.4 ? "moderate" : Math.abs(v) >= 0.2 ? "weak" : "negligible");
  const okCount = meta.status === "success" ? Object.values(meta.data.methods).filter((m) => m.status === "ok").length : null;
  const labelsMissing = relevance.length === 0 || relevance.every((r) => r.status === "not_computed");

  return (
    <div className="gx">
      <section className="xhero gx__hero" aria-label="Evaluation summary">
        <span className="gx__mark gx__mark--eval" aria-hidden="true"><Icon name="evaluation" size={32} /></span>
        <div className="xhero__id">
          <h1>Baselines &amp; evaluation</h1>
          <p>Stored STEP 21 results comparing the proposed Audience Bridge Score with the Louvain and node2vec baselines and its own components.</p>
          <p className="tx-note">Without relevance labels these results measure consistency between methods (agreement, stability, robustness), not correctness. Agreement with a baseline does not prove either method is right.</p>
        </div>
        {meta.status === "success" && (
          <div className="xhero__facts">
            <div><strong>{okCount}/{Object.keys(meta.data.methods).length}</strong><span>methods evaluated</span></div>
            <div><strong>{labelsMissing ? "none" : "yes"}</strong><span>relevance labels</span></div>
            <div><strong>{int(Number(meta.data.sparse_robustness.runs ?? 0))}</strong><span>sparse simulations</span></div>
          </div>
        )}
      </section>

      {runs.data.items.length === 0 ? (
        <QuickSkipNotice what="The evaluation" fallback={
          <EmptyState title="No evaluation has been run for this snapshot">
            <p>Run python -m research.component_3.evaluation.evaluate to produce evaluation results.</p>
          </EmptyState>} />
      ) : (
        <>
          <div className="ev-bar">
            <label><span>Evaluation run</span>
              <select id="eval-run" value={evaluationId} onChange={(e) => setSelected(e.target.value)}>
                {runs.data.items.map((r) => <option key={r.evaluation_id} value={r.evaluation_id}>{r.evaluation_id} ({date(r.created_at)})</option>)}
              </select>
            </label>
            {meta.status === "success" && <span className="ev-bar__meta">as of {date(meta.data.as_of as string | null)} · created {date(meta.data.created_at)}</span>}
          </div>

          {meta.status === "loading" && <Loading variant="cards" rows={3} />}
          {meta.status === "error" && <ErrorState error={meta.error} onRetry={meta.reload} what="Evaluation metadata" />}

          {meta.status === "success" && (
            <section className="xblock" aria-label="Methods compared">
              <header className="xblock__head"><div><h3>Methods compared</h3><p>The proposed score in the middle; each connector shows its Spearman rank agreement with a baseline.</p></div></header>
              <div className="ev-compare">
                {(["louvain", "audience_bridge_score", "node2vec"] as const).map((key, idx) => {
                  const g = METHOD_GROUPS.find((x) => x.method === key)!;
                  const m = meta.data.methods[key];
                  const card = (
                    <article key={key} className={`ev-card${key === "audience_bridge_score" ? " ev-card--main" : ""}`}>
                      <span className="ev-card__kicker">{g.title}</span>
                      <strong>{g.kind}</strong>
                      <p>{g.note}</p>
                      <span>{m ? <Badge tone={m.status === "ok" ? "ok" : "warn"}>{scalar(m.status)}</Badge> : <Badge tone="neutral">not in this run</Badge>}</span>
                    </article>
                  );
                  if (idx === 1) return card;
                  const v = spear(key);
                  const link = (
                    <div key={`${key}-link`} className={`ev-link ev-link--${tone(v)}`}>
                      <span className="ev-link__line" />
                      <span className="ev-link__pill"><small>Spearman</small><b>{num(v)}</b><em>{tone(v) === "none" ? "not computed" : tone(v)}</em></span>
                    </div>
                  );
                  return idx === 0 ? [card, link] : [link, card];
                })}
              </div>
            </section>
          )}

          {ranking.status === "success" && proposedVs.length > 0 && (
            <section className="xblock" aria-label="Key results">
              <header className="xblock__head"><div><h3>Agreement with the proposed score</h3><p>Every stored agreement metric between the proposed score and each other method. Bars run from −1 to 1; consistency, not correctness.</p></div></header>
              <div className="ev-agree">
                {proposedVs.map((a) => {
                  const other = String(a.method === "audience_bridge_score" ? a.reference_method : a.method);
                  return (
                    <div key={other} className="ev-agree__row">
                      <span className="ev-agree__name">{label(other)}</span>
                      <ul>
                        {agreementCols.filter((c2) => typeof a[c2] === "number").map((c2) => {
                          const v = a[c2] as number, signed = c2.startsWith("spearman") || c2.startsWith("kendall");
                          const w = Math.min(50, Math.abs(v) * 50);
                          return (
                            <li key={c2} title={interpret(c2, v)}>
                              <span className="ev-agree__metric"><Metric name={c2.split("@")[0]} />{c2.includes("@") ? `@${c2.split("@")[1]}` : ""}</span>
                              <span className="ev-agree__track">
                                <i className={v < 0 ? "is-neg" : ""} style={signed ? { left: v < 0 ? `${50 - w}%` : "50%", width: `${w}%` } : { left: "50%", width: `${Math.min(50, v * 50)}%` }} />
                                <span className="ev-agree__zero" />
                              </span>
                              <b>{num(v)}</b>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <div className="ev-status">
            <section className="ev-stat" aria-label="Ranking quality (relevance metrics)">
              <span className="ev-stat__icon"><Icon name="evaluation" size={18} /></span>
              <h3>Ranking quality</h3>
              {ranking.status === "loading" && <Loading variant="block" />}
              {ranking.status === "error" && <ErrorState error={ranking.error} onRetry={ranking.reload} what="Ranking results" />}
              {ranking.status === "success" && (labelsMissing ? (
                <p><Badge tone="neutral">Not available</Badge> Ground-truth relevance labels unavailable. Precision@k, Recall@k, NDCG@k and MRR need explicit relevance labels, so no accuracy is reported.</p>
              ) : (
                <RowsTable caption="Relevance metrics" rows={relevance} columns={["method", "metric", "k", "value", "n_sources", "status"]} />
              ))}
            </section>
            <section className="ev-stat" aria-label="Temporal stability">
              <span className="ev-stat__icon"><Icon name="overview" size={18} /></span>
              <h3>Temporal stability</h3>
              {temporal.status === "loading" && <Loading variant="block" />}
              {temporal.status === "error" && <ErrorState error={temporal.error} onRetry={temporal.reload} what="Temporal stability" />}
              {temporal.status === "success" && (temporal.data.items.length === 0 ? <p className="muted">Temporal stability was not run.</p> :
                temporal.data.items.every((r) => r.status === "insufficient_temporal_data" || r.status === "not_comparable") ? (
                  <p><Badge tone="neutral">Insufficient temporal data</Badge> {scalar(temporal.data.items.find((r) => r.reason)?.reason ?? null)}</p>
                ) : (
                  <p><Badge tone="ok">Computed</Badge> {temporal.data.items.filter((r) => r.status === "ok").length} snapshot comparisons across {new Set(temporal.data.items.map((r) => r.method)).size} methods. Full results below.</p>
                ))}
            </section>
            <section className="ev-stat" aria-label="Sparse-data robustness">
              <span className="ev-stat__icon"><Icon name="graph" size={18} /></span>
              <h3>Sparse-data robustness</h3>
              {sparse.status === "loading" && <Loading variant="block" />}
              {sparse.status === "error" && <ErrorState error={sparse.error} onRetry={sparse.reload} what="Sparse-data robustness" />}
              {sparse.status === "success" && (sparse.data.items.length === 0 ? (
                <p><Badge tone="neutral">Not run</Badge> This evaluation was run without sparse-data simulations.</p>
              ) : (
                <p><Badge tone="ok">Computed</Badge> {sparse.data.items.length} results from seeded comment subsamples across {new Set(sparse.data.items.map((r) => r.method)).size} methods. Full results below.</p>
              ))}
            </section>
          </div>
          {temporal.status === "success" && temporal.data.items.some((r) => r.status === "ok") && (
            <section className="xblock" aria-label="Temporal stability results">
              <header className="xblock__head"><div><h3>Temporal stability results</h3><p>How each method's rankings change between an earlier and a later snapshot of the same channels.</p></div></header>
              <RowsTable caption="Temporal stability" rows={temporal.data.items.filter((r) => r.status === "ok")} columns={["method", "earlier_snapshot_id", "later_snapshot_id", "metric", "k", "value", "n_sources"]} />
            </section>
          )}
          {sparse.status === "success" && sparse.data.items.length > 0 && (
            <section className="xblock" aria-label="Sparse-data robustness results">
              <header className="xblock__head"><div><h3>Sparse-data robustness results</h3><p>Agreement of each method's rankings with the full-data rankings when only part of the comments is kept.</p></div></header>
              <RowsTable caption="Sparse-data robustness" rows={sparse.data.items} columns={["method", "unit", "retain_fraction", "seed", "metric", "k", "value", "n_sources", "status"]} />
            </section>
          )}
          {statusRows.length > 0 && <RowsTable caption="Unavailable methods" rows={statusRows} columns={["method", "status", "reason"]} />}

          <div className="xgrid xgrid--2">
            <section className="xblock" aria-label="Ranking consistency between methods">
              <header className="xblock__head"><div><h3>Spearman agreement</h3><p>The proposed score against each baseline and component.</p></div></header>
              {ranking.status === "success" && agreement.length === 0 && <p className="muted">No agreement results in this run.</p>}
              {proposedVs.length > 0 && (
                <HorizontalBarChart title="Spearman agreement of the Audience Bridge Score with each method" unit="correlation" min={-1} max={1}
                  bars={proposedVs.map((a) => {
                    const other = a.method === "audience_bridge_score" ? a.reference_method : a.method;
                    return { key: String(other), label: label(String(other)), value: typeof a.spearman === "number" ? a.spearman : null };
                  })} />
              )}
            </section>
            {meta.status === "success" && (
              <section className="xblock" aria-label="All methods in this run">
                <header className="xblock__head"><div><h3>All methods in this run</h3><p>{meta.data.interpretation ? scalar(meta.data.interpretation) : "Each method's role and status."}</p></div></header>
                <ul className="ev-methods">
                  {Object.entries(meta.data.methods).map(([m, v]) => (
                    <li key={m}>
                      <span className={`ev-methods__dot ${v.status === "ok" ? "is-ok" : ""}`} />
                      <span className="ev-methods__name"><b>{label(m)}</b><small>{scalar(v.role)}{v.reason ? ` · ${scalar(v.reason)}` : ""}</small></span>
                      <Badge tone={v.status === "ok" ? "ok" : "warn"}>{scalar(v.status)}</Badge>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          {agreement.length > 0 && (
            <section className="xblock" aria-label="Agreement table">
              <header className="xblock__head"><div><h3>All agreement results</h3><p>Every stored pairwise agreement metric, with the number of source channels compared.</p></div></header>
              <TableWrap label="Agreement">
                <table className="table table--compact">
                  <thead>
                    <tr>
                      <th scope="col">Method</th><th scope="col">Compared with</th>
                      {agreementCols.map((c2) => <th scope="col" className="num" key={c2}><Metric name={c2.split("@")[0]} />{c2.includes("@") ? `@${c2.split("@")[1]}` : ""}</th>)}
                      <th scope="col" className="num">Sources</th>
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
            </section>
          )}

          <section className="xblock" aria-label="Top-k results">
            <header className="xblock__head">
              <div><h3>Top-k results</h3><p>Summary of each method's top-k lists, and the stored lists themselves.</p></div>
              <label className="tx-k"><span>Method</span>
                <select id="topk-method" aria-label="Top-k lists for method" value={topkMethod} onChange={(e) => setTopkMethod(e.target.value)}>
                  {(meta.status === "success" ? Object.keys(meta.data.methods) : [topkMethod]).map((m) => <option key={m} value={m}>{label(m)}</option>)}
                </select>
              </label>
            </header>
            <RowsTable caption="Top-k summary" rows={rows.filter((r) => r.analysis === "top_k_summary")} columns={["method", "metric", "k", "value", "n_sources", "status"]} />
            {topk.status === "loading" && <Loading variant="table" />}
            {topk.status === "error" && <ErrorState error={topk.error} onRetry={topk.reload} what="Top-k lists" />}
            {topk.status === "success" && (topk.data.items.length === 0 ? <p className="muted">No top-k rows for this method.</p> : (
              <>
                <RowsTable caption="Top-k destinations" columns={["source", "rank", "destination", "score", "tied"]}
                  rows={topk.data.items.map((r) => ({ ...r, source: channelName(channels.status === "success" ? channels.data.items : [], r.source_channel_id as string), destination: channelName(channels.status === "success" ? channels.data.items : [], r.destination_channel_id as string) }))} />
                {topk.data.total > topk.data.items.length && <p className="muted">Showing the first {topk.data.items.length} of {topk.data.total} rows.</p>}
              </>
            ))}
          </section>

          <section className="xblock" aria-label="Computational performance">
            <header className="xblock__head"><div><h3>Computational performance</h3><p>Measured time and memory per pipeline stage.</p></div></header>
            {perf.status === "loading" && <Loading variant="table" />}
            {perf.status === "error" && <ErrorState error={perf.error} onRetry={perf.reload} what="Performance" />}
            {perf.status === "success" && (
              <>
                <RowsTable caption="Measured performance" rows={perf.data.items} columns={["stage", "method", "status", "seconds", "python_heap_peak_mib", "graph_nodes", "graph_edges"]} />
                {meta.status === "success" && <p className="xnote">{scalar(meta.data.performance.memory_note ?? null)}</p>}
              </>
            )}
          </section>
          <Provenance snapshotId={runs.data.snapshot_id} extra={`Evaluation ${evaluationId}`} />
        </>
      )}
    </div>
  );
}
