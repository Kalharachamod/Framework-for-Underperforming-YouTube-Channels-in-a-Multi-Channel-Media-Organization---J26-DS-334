import { Fragment, useMemo, useState } from "react";
import { ChannelAvatar } from "../../../components/common/ChannelAvatar";
import { useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Notice, PageHeader, Pager, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { BridgeExplorer } from "../BridgeExplorer";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { BridgePairRow } from "../types";

const PAGE = 20;
type SortKey = "order" | "score" | "confidence" | "diffusion" | "topic" | "shared";
const SORTS: Record<SortKey, (r: BridgePairRow) => number | null> = {
  order: () => null,
  score: (r) => r.audience_bridge_score,
  confidence: (r) => r.confidence_component,
  diffusion: (r) => r.diffusion_component,
  topic: (r) => r.topic_similarity ?? null,
  shared: (r) => r.shared_commenters,
};

/** Expanded row: aggregate evidence of one pair, loaded only when the row is opened. */
function EvidenceRow({ row, cols }: { row: BridgePairRow; cols: number }) {
  const { snapshotId, experimentId } = useResearch();
  const pair = useApi((s) => component3Api.pair(row.source_channel_id, row.destination_channel_id, { snapshotId, experimentId }, s),
    [row.source_channel_id, row.destination_channel_id, snapshotId, experimentId]);
  return (
    <tr className="rt-expand">
      <td colSpan={cols}>
        {pair.status === "loading" || pair.status === "idle" ? <Loading variant="block" label="Loading evidence…" /> :
          pair.status === "error" ? <ErrorState error={pair.error} onRetry={pair.reload} what="Evidence" /> : pair.data.evidence_summary === null ? (
            <p className="muted small">No evidence row for this pair.</p>
          ) : (
            <dl className="rt-evidence">
              <div><dt>Shared commenters</dt><dd>{int(pair.data.evidence_summary.shared_commenters)}</dd></div>
              <div><dt>Interactions (source / destination)</dt><dd>{int(pair.data.evidence_summary.shared_comments_on_source)} / {int(pair.data.evidence_summary.shared_comments_on_destination)}</dd></div>
              <div><dt>Video coverage</dt><dd>{pct(pair.data.evidence_summary.source_video_coverage)} / {pct(pair.data.evidence_summary.destination_video_coverage)}</dd></div>
              <div><dt>Temporal support</dt><dd>{int(pair.data.evidence_summary.shared_active_days)} active days</dd></div>
              <div><dt>Base score · embedding component</dt><dd>{num(row.base_score, 3)} · {num(row.embedding_component, 3)}</dd></div>
            </dl>
          )}
      </td>
    </tr>
  );
}

export function BridgesPage() {
  const { snapshotId, experimentId } = useResearch();
  const [params, setParams] = useSearchParams();
  const pairs = useApi((s) => component3Api.bridgePairs({ snapshotId, experimentId }, s), [snapshotId, experimentId]);
  const [query, setQuery] = useState("");
  const [fSource, setFSource] = useState("");
  const [fDest, setFDest] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [minConf, setMinConf] = useState(0);
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "order", desc: true });
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);

  const items = useMemo(() => (pairs.status === "success" ? pairs.data.items : []), [pairs]);
  const source = params.get("source") ?? "";
  const destination = params.get("destination") ?? "";
  const channels = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of items) m.set(r.source_channel_id, r.source_channel_name ?? r.source_channel_id);
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [items]);

  const table = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = items.filter((r) => (!fSource || r.source_channel_id === fSource) && (!fDest || r.destination_channel_id === fDest)
      && (r.audience_bridge_score ?? 0) >= minScore && (r.confidence_component ?? 0) >= minConf
      && (!q || `${r.source_channel_name} ${r.destination_channel_name}`.toLowerCase().includes(q)));
    if (sort.key !== "order") {
      const get = SORTS[sort.key];
      rows = [...rows].sort((a, b) => ((get(a) ?? -Infinity) - (get(b) ?? -Infinity)) * (sort.desc ? -1 : 1));
    }
    return rows;
  }, [items, query, fSource, fDest, minScore, minConf, sort]);
  const resetPage = () => { setOffset(0); setOpen(null); };
  const th = (key: SortKey, text: string, title?: string) => (
    <th scope="col" className="num" title={title} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button type="button" className="th-sort" onClick={() => { resetPage(); setSort((s) => ({ key, desc: s.key === key ? !s.desc : true })); }}>
        {text}{sort.key === key ? (sort.desc ? " ↓" : " ↑") : ""}
      </button>
    </th>
  );

  return (
    <>
      <PageHeader title="Audience Bridges" description="Directed potential audience bridges (source → destination) ranked by the stored Audience Bridge Score." />
      <Notice>{LIMITATIONS}</Notice>
      {pairs.status === "loading" && <Loading variant="graph" label="Loading scored pairs…" />}
      {pairs.status === "error" && <ErrorState error={pairs.error} onRetry={pairs.reload} what={`Bridge rankings${experimentId ? ` for experiment ${experimentId}` : ""}`} />}
      {pairs.status === "success" && items.length === 0 && <EmptyState title="No bridge relationships are available for this snapshot." />}
      {pairs.status === "success" && items.length > 0 && (
        <>
          <section className="ov-panel ov-panel--main" aria-label="Bridge network">
            <BridgeExplorer pairs={items} source={source} destination={destination}
              onSource={(id) => setParams(id ? { source: id } : {})} onPair={(s, d) => setParams({ source: s, destination: d })} />
          </section>

          <section className="ov-panel" aria-label="Ranking table">
            <header className="ov-panel__head">
              <h2>Bridge ranking</h2>
              <p>Rows follow the backend's deterministic order (score, then channel ids); sorting only reorders the display. Topic similarity is symmetric; the bridge score is directional.</p>
            </header>
            <div className="bx-filters">
              <label><span>Search</span><input type="search" placeholder="Channel name…" value={query} onChange={(e) => { resetPage(); setQuery(e.target.value); }} /></label>
              <label><span>Source</span><select value={fSource} onChange={(e) => { resetPage(); setFSource(e.target.value); }}><option value="">All sources</option>{channels.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
              <label><span>Destination</span><select value={fDest} onChange={(e) => { resetPage(); setFDest(e.target.value); }}><option value="">All destinations</option>{channels.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>
              <label><span>Min score {num(minScore, 2)}</span><input type="range" min={0} max={1} step={0.05} value={minScore} onChange={(e) => { resetPage(); setMinScore(Number(e.target.value)); }} /></label>
              <label><span>Min confidence {num(minConf, 2)}</span><input type="range" min={0} max={1} step={0.05} value={minConf} onChange={(e) => { resetPage(); setMinConf(Number(e.target.value)); }} /></label>
              <span className="bx-filters__count">{int(table.length)} of {int(items.length)} pairs</span>
            </div>
            {table.length === 0 ? <EmptyState title="No pair matches these filters." /> : (
              <>
                <TableWrap label="Top bridge opportunities">
                  <table className="table table--compact rt">
                    <thead>
                      <tr>
                        <th scope="col"><span className="sr-only">Expand</span></th>
                        <th scope="col" title="Rank among the source's destinations (from the scoring run)">Rank</th>
                        <th scope="col">Source → Destination</th>
                        {th("score", "Bridge score")}
                        {th("confidence", "Confidence")}
                        {th("diffusion", "Diffusion", "Diffusion component (weight × normalised Personalized PageRank)")}
                        {th("topic", "Topic sim.", "Raw cosine similarity of the two content profiles (symmetric)")}
                        {th("shared", "Evidence", "Shared commenters (aggregate)")}
                        <th scope="col" className="col-optional">Snapshot</th>
                      </tr>
                    </thead>
                    <tbody>
                      {table.slice(offset, offset + PAGE).map((r) => {
                        const key = `${r.source_channel_id}>${r.destination_channel_id}`;
                        const isOpen = open === key;
                        return (
                          <Fragment key={key}>
                            <tr className={r.source_channel_id === source && r.destination_channel_id === destination ? "is-on" : ""}>
                              <td><button type="button" className="rt-toggle" aria-expanded={isOpen} aria-label={`${isOpen ? "Hide" : "Show"} evidence for ${r.source_channel_name} to ${r.destination_channel_name}`}
                                onClick={() => setOpen(isOpen ? null : key)}>{isOpen ? "−" : "+"}</button></td>
                              <td>{r.rank ?? "—"}</td>
                              <td className="rt-pair">
                                <button type="button" className="link-button rt-pairbtn" onClick={() => { setParams({ source: r.source_channel_id, destination: r.destination_channel_id }); window.scrollTo?.({ top: 0, behavior: "smooth" }); }}>
                                  <ChannelAvatar id={r.source_channel_id} name={r.source_channel_name} size={20} />
                                  {r.source_channel_name} <span aria-hidden="true">→</span> <ChannelAvatar id={r.destination_channel_id} name={r.destination_channel_name} size={20} /> {r.destination_channel_name}
                                </button>
                              </td>
                              <td className="num rt-score">{num(r.audience_bridge_score, 3)}</td>
                              <td className="num">{num(r.confidence_component, 3)}</td>
                              <td className="num">{num(r.diffusion_component, 3)}</td>
                              <td className="num">{num(r.topic_similarity ?? null, 3)}</td>
                              <td className="num">{int(r.shared_commenters)}</td>
                              <td className="col-optional muted small mono">{pairs.data.snapshot_id}</td>
                            </tr>
                            {isOpen && <EvidenceRow row={r} cols={9} />}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </TableWrap>
                <Pager total={table.length} limit={PAGE} offset={offset} onChange={(o) => { setOffset(o); setOpen(null); }} />
              </>
            )}
          </section>
          <Provenance snapshotId={pairs.data.snapshot_id} experimentId={pairs.data.experiment_id} />
        </>
      )}
    </>
  );
}
