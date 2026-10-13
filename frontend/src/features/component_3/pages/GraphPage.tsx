import { Link } from "react-router-dom";
import { Histogram } from "../../../components/charts/Matrix";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { Scalar } from "../types";

const TYPE_ORDER = ["channel", "video", "commenter", "topic"];
const scalar = (v: Scalar | undefined) => (v === null || v === undefined ? "—" : typeof v === "number"
  ? (Number.isInteger(v) ? int(v) : Math.abs(v) < 1e-3 ? v.toExponential(2) : String(Number(v.toPrecision(6)))) : String(v));

export function GraphPage() {
  const { snapshotId } = useResearch();
  const g = useApi((s) => component3Api.graphSummary({ snapshotId }, s), [snapshotId]);

  return (
    <>
      <PageHeader title="Graph Intelligence" description="The heterogeneous research graph, its learned representations and the Personalized PageRank diffusion that feed the Audience Bridge Score." />
      {g.status === "loading" && <Loading label="Loading graph summary…" />}
      {g.status === "error" && <ErrorState error={g.error} onRetry={g.reload} />}
      {g.status === "success" && (() => {
        const d = g.data;
        const types = [...Object.keys(d.node_counts)].sort((a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b));
        const isolated = d.connected_components.filter((c) => c === 1).length;
        return (
          <>
            <section className="rs-strip" aria-label="Graph summary">
              {types.map((t) => (
                <div key={t} className="rs-strip__cell"><span>{label(t)} nodes</span><strong>{int(d.node_counts[t])}</strong></div>
              ))}
              <div className="rs-strip__cell"><span>Total edges</span><strong>{int(d.total_edges)}</strong><small>{int(d.total_edges_excluding_derived)} observed</small></div>
            </section>

            <div className="grid grid--2">
              <Card title="Graph structure" info="Relations of the heterogeneous graph (STEP 13). Derived relations summarise observed ones and are not used for diffusion by default.">
                <TableWrap label="Relations">
                  <table className="table table--compact">
                    <thead><tr><th scope="col">Relation</th><th scope="col">From → to</th><th scope="col" className="num">Edges</th><th scope="col">Kind</th></tr></thead>
                    <tbody>
                      {d.relations.map((r) => (
                        <tr key={r.relation} title={r.weight_definition ?? undefined}>
                          <td><code>{r.relation}</code></td>
                          <td>{r.source_type} → {r.target_type}</td>
                          <td className="num">{int(r.edges)}</td>
                          <td>{r.derived ? <Badge tone="neutral">derived</Badge> : <Badge tone="ok">observed</Badge>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
                <KeyValues rows={[
                  ["Commenters on 2+ channels", int(d.commenters_on_multiple_channels)],
                  ["Channel pairs sharing commenters", int(d.channel_pairs_with_shared_commenters)],
                  ["Connected components (channel overlap graph)", `${d.connected_components.length} · largest ${int(d.connected_components[0])} channels · ${isolated} isolated`],
                  ["Built", date(d.built_at)],
                ]} />
              </Card>
              <Card title="Channel connectivity" info="Channels ranked by how many other research channels share at least one commenter with them. Summed shared commenters count a person once per channel pair.">
                {d.channel_connectivity.length === 0 ? <EmptyState title="No channel overlap available" /> : (
                  <TableWrap label="Channel connectivity">
                    <table className="table table--compact">
                      <thead><tr><th scope="col">Channel</th><th scope="col" className="num">Connected channels</th><th scope="col" className="num">Shared (summed)</th></tr></thead>
                      <tbody>
                        {d.channel_connectivity.map((c) => (
                          <tr key={c.channel_id}>
                            <td><Link to={`/channels?channel=${encodeURIComponent(c.channel_id)}`}>{c.channel_name ?? c.channel_id}</Link></td>
                            <td className="num">{c.connected_channels === 0 ? <span className="muted">isolated</span> : int(c.connected_channels)}</td>
                            <td className="num">{int(c.shared_commenters_summed)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableWrap>
                )}
              </Card>
            </div>

            <Card title="Degree distribution" info="Number of nodes per degree bin, counting observed (non-derived) edges only. Counts only: no node is identified.">
              <div className="hist-grid">
                {d.degree_distribution.sort((a, b) => TYPE_ORDER.indexOf(a.node_type) - TYPE_ORDER.indexOf(b.node_type)).map((x) => (
                  <div key={x.node_type} className="hist-grid__item">
                    <div className="hist-grid__head">
                      <strong>{label(x.node_type)}</strong>
                      <span className="muted">{int(x.nodes)} nodes · mean {num(x.mean_degree, 2)} · max {int(x.max_degree)}</span>
                    </div>
                    <Histogram bins={x.bins} label={`${label(x.node_type)} degree distribution`} />
                  </div>
                ))}
              </div>
            </Card>

            <div className="grid grid--2">
              <Card title="Representation learning" info="Stored graph-embedding runs. metapath2vec is the primary embedding source of the score; HGT is the alternative.">
                <div className="rep-list">
                  {d.representations.map((r) => (
                    <div key={r.method} className="rep">
                      <div className="rep__head">
                        <strong>{r.method}</strong>
                        {r.status === "missing" ? <Badge tone="neutral">Not run</Badge> : <Badge tone={r.validation_passed ? "ok" : "warn"}>{r.validation_passed ? "Validated" : "Not validated"}</Badge>}
                      </div>
                      {r.status === "available" ? (
                        <KeyValues rows={[
                          ["Run", <code key="r">{r.experiment_id}</code>],
                          ["Role", r.role ?? "—"],
                          ["Dimensions", int(r.dimensions)],
                          ["Coverage", pct(r.coverage_ratio, 1)],
                          ...Object.entries(r.config ?? {}).slice(0, 5).map(([k, v]) => [label(k), scalar(v)] as [string, string]),
                        ]} />
                      ) : <p className="muted">No stored run for this snapshot.</p>}
                    </div>
                  ))}
                </div>
              </Card>
              <Card title="Diffusion (Personalized PageRank)" info="Settings and convergence recorded by the stored diffusion run (STEP 17).">
                {d.diffusion.status === "missing" ? <EmptyState title="Not run"><p>No diffusion run is stored for this snapshot.</p></EmptyState> : (
                  <>
                    <p className="conv">
                      <Badge tone={d.diffusion.converged_sources === d.diffusion.sources ? "ok" : "warn"}>
                        {int(d.diffusion.converged_sources)} / {int(d.diffusion.sources)} sources converged
                      </Badge>
                    </p>
                    <KeyValues rows={[
                      ["Run", <code key="r">{d.diffusion.experiment_id}</code>],
                      ["Alpha (damping)", scalar(d.diffusion.alpha)],
                      ["Tolerance", d.diffusion.tolerance === null || d.diffusion.tolerance === undefined ? "—" : d.diffusion.tolerance.toExponential(0)],
                      ["Iterations (max used / limit)", `${int(d.diffusion.iterations_max)} / ${int(d.diffusion.max_iterations)}`],
                      ["Largest final residual", d.diffusion.residual_max === null || d.diffusion.residual_max === undefined ? "—" : d.diffusion.residual_max.toExponential(2)],
                      ["Directionality", scalar(d.diffusion.directionality)],
                      ["Topic edges in diffusion", d.diffusion.include_topic_edges ? "included" : "excluded"],
                      ["Diffusion graph", `${int(d.diffusion.graph_nodes)} nodes · ${int(d.diffusion.graph_edges)} edges`],
                    ]} />
                  </>
                )}
              </Card>
            </div>
            <p className="muted small">{d.note}</p>
            <Provenance snapshotId={d.snapshot_id} />
          </>
        );
      })()}
    </>
  );
}
