import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BridgeTree } from "../../../components/charts/BridgeTree";
import { EgoNetwork } from "../../../components/charts/BridgeViz";
import { ScoreBreakdown } from "../../../components/charts/ScoreBreakdown";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, Notice, PageHeader, Pager, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { BridgePairRow } from "../types";

const PAGE = 20;
const DEPTHS = [3, 5, 10, 17] as const;
type SortKey = "order" | "score" | "diffusion" | "topic" | "confidence" | "shared";
const SORTS: Record<SortKey, (r: BridgePairRow) => number | null> = {
  order: () => null,
  score: (r) => r.audience_bridge_score,
  diffusion: (r) => r.diffusion_component,
  topic: (r) => r.topic_component,
  confidence: (r) => r.confidence_component,
  shared: (r) => r.shared_commenters,
};

/** Selected-bridge analysis: stored decomposition and aggregate evidence of one pair. */
function BridgeAnalysis({ source, destination }: { source: string; destination: string }) {
  const { snapshotId, experimentId } = useResearch();
  const pair = useApi((s) => component3Api.pair(source, destination, { snapshotId, experimentId }, s),
    [source, destination, snapshotId, experimentId], source !== "" && destination !== "" && source !== destination);
  if (pair.status === "loading" || pair.status === "idle") return <Loading label="Loading bridge…" />;
  if (pair.status === "error") return <ErrorState error={pair.error} onRetry={pair.reload} />;
  const p = pair.data, b = p.score_breakdown, e = p.evidence_summary;
  return (
    <div className="bx-analysis">
      <p className="bx-analysis__pair">{p.source_channel_name} <span aria-hidden="true">→</span> {p.destination_channel_name}</p>
      <div className="bx-analysis__score">
        <span>Audience Bridge Score</span>
        <strong>{num(p.audience_bridge_score, 3)}</strong>
        <span className="muted">rank {p.rank ?? "—"}{p.ranking_context ? ` of ${int(p.ranking_context.scored_destinations)}` : ""} for this source</span>
      </div>
      <ScoreBreakdown compact b={{ diffusion: b.diffusion_component, embedding: b.embedding_component, topic: b.topic_component,
        base: b.base_score, confidence: b.confidence_component, score: p.audience_bridge_score, embeddingUsed: b.w_embedding > 0 }} />
      <details className="bx-evidence" open>
        <summary>Evidence (aggregate)</summary>
        {e === null ? <p className="muted">No evidence row for this pair.</p> : (
          <dl className="bx-evidence__list">
            <div><dt>Shared commenters</dt><dd>{int(e.shared_commenters)}</dd></div>
            <div><dt>Interactions (comments by shared commenters)</dt><dd>{int(e.shared_comments_on_source)} / {int(e.shared_comments_on_destination)}</dd></div>
            <div><dt>Video coverage (source / destination)</dt><dd>{pct(e.source_video_coverage)} / {pct(e.destination_video_coverage)}</dd></div>
            <div><dt>Temporal support</dt><dd>{int(e.shared_active_days)} active days</dd></div>
            <div><dt>Data coverage (topic profiles)</dt><dd>{num(b.topic_coverage_confidence, 2)}</dd></div>
            <div><dt>Evidence confidence</dt><dd>{num(b.evidence_confidence, 3)}</dd></div>
          </dl>
        )}
      </details>
      <Link className="bx-analysis__link" to={`/explainability?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`}>Full explanation →</Link>
    </div>
  );
}

export function BridgesPage() {
  const { snapshotId, experimentId } = useResearch();
  const [params, setParams] = useSearchParams();
  const pairs = useApi((s) => component3Api.bridgePairs({ snapshotId, experimentId }, s), [snapshotId, experimentId]);
  const [filter, setFilter] = useState("");
  const [depth, setDepth] = useState<number>(5);
  const [view, setView] = useState<"tree" | "radial">("tree");
  const [fSource, setFSource] = useState("");
  const [fDest, setFDest] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [minConf, setMinConf] = useState(0);
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "order", desc: true });
  const [offset, setOffset] = useState(0);

  const items = useMemo(() => (pairs.status === "success" ? pairs.data.items : []), [pairs]);
  const sources = useMemo(() => {
    const best = new Map<string, { id: string; name: string; top: number | null }>();
    for (const r of items) {
      const cur = best.get(r.source_channel_id);
      const s = r.audience_bridge_score;
      if (!cur) best.set(r.source_channel_id, { id: r.source_channel_id, name: r.source_channel_name ?? r.source_channel_id, top: s });
      else if (s !== null && (cur.top === null || s > cur.top)) cur.top = s;
    }
    return [...best.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [items]);

  const source = params.get("source") ?? (items[0]?.source_channel_id ?? "");
  const outgoing = items.filter((r) => r.source_channel_id === source && r.audience_bridge_score !== null)
    .sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9));
  const destination = params.get("destination") ?? (outgoing[0]?.destination_channel_id ?? "");
  const setPair = (s: string, d?: string) => setParams(d ? { source: s, destination: d } : { source: s });
  const sourceName = sources.find((s) => s.id === source)?.name ?? source;

  const table = useMemo(() => {
    let rows = items.filter((r) => (!fSource || r.source_channel_id === fSource) && (!fDest || r.destination_channel_id === fDest)
      && (r.audience_bridge_score ?? 0) >= minScore && (r.confidence_component ?? 0) >= minConf);
    if (sort.key !== "order") {
      const get = SORTS[sort.key];
      rows = [...rows].sort((a, b) => ((get(a) ?? -Infinity) - (get(b) ?? -Infinity)) * (sort.desc ? -1 : 1));
    }
    return rows;
  }, [items, fSource, fDest, minScore, minConf, sort]);
  const th = (key: SortKey, text: string) => (
    <th scope="col" className="num" aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button type="button" className="th-sort" onClick={() => { setOffset(0); setSort((s) => ({ key, desc: s.key === key ? !s.desc : true })); }}>
        {text}{sort.key === key ? (sort.desc ? " ↓" : " ↑") : ""}
      </button>
    </th>
  );
  const channelOptions = sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>);

  return (
    <>
      <PageHeader title="Audience Bridges" description="Potential audience bridges between channels, ranked by the stored Audience Bridge Score. Select a source, then a destination to see why it scored as it did." />
      <Notice>{LIMITATIONS}</Notice>
      {pairs.status === "loading" && <Loading label="Loading scored pairs…" />}
      {pairs.status === "error" && <ErrorState error={pairs.error} onRetry={pairs.reload} />}
      {pairs.status === "success" && items.length === 0 && <EmptyState title="No research data available for this snapshot." />}
      {pairs.status === "success" && items.length > 0 && (
        <>
          <div className="bx">
            <nav className="bx-sources" aria-label="Source channels">
              <label className="bx-sources__search">
                <span className="sr-only">Filter source channels</span>
                <input type="search" placeholder="Filter channels…" value={filter} onChange={(e) => setFilter(e.target.value)} />
              </label>
              <ul>
                {sources.filter((s) => s.name.toLowerCase().includes(filter.trim().toLowerCase())).map((s) => (
                  <li key={s.id}>
                    <button type="button" className={s.id === source ? "is-on" : ""} aria-pressed={s.id === source} onClick={() => setPair(s.id)}>
                      <span className="bx-sources__name">{s.name}</span>
                      <span className="bx-sources__top" title="Highest score among this source's destinations">{num(s.top, 3)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>

            <section className="bx-center" aria-label="Bridge network">
              <header className="bx-center__head">
                <div>
                  <h2>{sourceName}</h2>
                  <p>{outgoing.length} scored destinations · select a node to analyse the bridge</p>
                </div>
                <div className="segmented" role="group" aria-label="Graph view">
                  {(["tree", "radial"] as const).map((v) => (
                    <button key={v} type="button" className={view === v ? "is-active" : ""} aria-pressed={view === v} onClick={() => setView(v)}>{v === "tree" ? "Tree" : "Radial"}</button>
                  ))}
                </div>
                <label className="bx-depth">
                  <span>Ranking depth</span>
                  <select value={depth} onChange={(e) => setDepth(Number(e.target.value))} aria-label="Ranking depth">
                    {DEPTHS.map((d) => <option key={d} value={d}>{d === 17 ? "All" : `Top ${d}`}</option>)}
                  </select>
                </label>
              </header>
              {outgoing.length === 0 ? <EmptyState title="This source has no scored destination in the selected experiment." /> : (
                view === "tree" ? (
                  <BridgeTree source={{ id: source, label: sourceName }} selected={destination} onSelect={(d) => setPair(source, d)}
                    subtitle={`Top ${Math.min(depth, outgoing.length)} of ${outgoing.length} scored destinations`}
                    targets={outgoing.slice(0, depth).map((r) => ({ id: r.destination_channel_id, label: r.destination_channel_name ?? r.destination_channel_id,
                      score: r.audience_bridge_score, confidence: r.confidence_component, rank: r.rank, shared: r.shared_commenters }))} />
                ) : (
                  <EgoNetwork source={{ id: source, label: sourceName }} depth={depth} selected={destination}
                    onSelect={(d) => setPair(source, d)}
                    targets={outgoing.map((r) => ({ id: r.destination_channel_id, label: r.destination_channel_name ?? r.destination_channel_id,
                      score: r.audience_bridge_score, confidence: r.confidence_component, rank: r.rank }))} />
                )
              )}
            </section>

            <aside className="bx-side" aria-label="Selected bridge analysis">
              <h2 className="bx-side__title">Selected bridge</h2>
              {destination ? <BridgeAnalysis source={source} destination={destination} /> : <EmptyState title="Select a destination." />}
            </aside>
          </div>

          <Card title="Top bridge opportunities" info="All stored scored pairs in the backend's deterministic order (score, then channel ids). Sorting only reorders the display; no score is recalculated.">
            <div className="bx-filters">
              <label><span>Source</span><select value={fSource} onChange={(e) => { setOffset(0); setFSource(e.target.value); }}><option value="">All sources</option>{channelOptions}</select></label>
              <label><span>Destination</span><select value={fDest} onChange={(e) => { setOffset(0); setFDest(e.target.value); }}><option value="">All destinations</option>{channelOptions}</select></label>
              <label><span>Min score {num(minScore, 2)}</span><input type="range" min={0} max={1} step={0.05} value={minScore} onChange={(e) => { setOffset(0); setMinScore(Number(e.target.value)); }} /></label>
              <label><span>Min confidence {num(minConf, 2)}</span><input type="range" min={0} max={1} step={0.05} value={minConf} onChange={(e) => { setOffset(0); setMinConf(Number(e.target.value)); }} /></label>
              <span className="bx-filters__count">{int(table.length)} of {int(items.length)} pairs</span>
            </div>
            {table.length === 0 ? <EmptyState title="No pair matches these filters." /> : (
              <>
                <TableWrap label="Top bridge opportunities">
                  <table className="table table--compact">
                    <thead>
                      <tr>
                        <th scope="col" title="Rank among the source's destinations, from the scoring run">Rank</th>
                        <th scope="col">Source</th>
                        <th scope="col">Destination</th>
                        {th("score", "Bridge score")}
                        {th("diffusion", "Diffusion")}
                        {th("topic", "Topic")}
                        {th("confidence", "Confidence")}
                        {th("shared", "Evidence")}
                        <th scope="col" className="col-optional">Snapshot</th>
                      </tr>
                    </thead>
                    <tbody>
                      {table.slice(offset, offset + PAGE).map((r) => (
                        <tr key={`${r.source_channel_id}-${r.destination_channel_id}`} className={r.source_channel_id === source && r.destination_channel_id === destination ? "is-on" : ""}>
                          <td>{r.rank ?? "—"}</td>
                          <td>{r.source_channel_name}</td>
                          <td>{r.destination_channel_name}</td>
                          <td className="num"><button type="button" className="link-button bx-score" onClick={() => { setPair(r.source_channel_id, r.destination_channel_id); window.scrollTo?.({ top: 0, behavior: "smooth" }); }}>{num(r.audience_bridge_score, 3)}</button></td>
                          <td className="num">{num(r.diffusion_component, 3)}</td>
                          <td className="num">{num(r.topic_component, 3)}</td>
                          <td className="num">{num(r.confidence_component, 3)}</td>
                          <td className="num" title="Shared commenters (aggregate)">{int(r.shared_commenters)}</td>
                          <td className="col-optional muted small"><code>{pairs.data.snapshot_id}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
                <Pager total={table.length} limit={PAGE} offset={offset} onChange={setOffset} />
              </>
            )}
            <p className="muted small">{pairs.data.note} {items.some((r) => r.score_status !== "ok") && <Badge tone="warn">some pairs have an incomplete score</Badge>}</p>
          </Card>
          <Provenance snapshotId={pairs.data.snapshot_id} experimentId={pairs.data.experiment_id} />
        </>
      )}
    </>
  );
}
