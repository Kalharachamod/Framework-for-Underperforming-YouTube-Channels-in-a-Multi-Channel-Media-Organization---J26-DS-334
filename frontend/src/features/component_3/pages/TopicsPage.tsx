import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Heatmap } from "../../../components/charts/Matrix";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, PageHeader, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";

export function TopicsPage() {
  const { snapshotId } = useResearch();
  const [params, setParams] = useSearchParams();
  const selected = params.get("channel") ?? undefined;
  const sim = useApi((s) => component3Api.topicSimilarity({ snapshotId }, s), [snapshotId]);
  const clusters = useApi((s) => component3Api.topics({ snapshotId }, s), [snapshotId]);

  const lookup = useMemo(() => {
    const m = new Map<string, number | null>();
    if (sim.status === "success") for (const c of sim.data.cells) m.set(`${c.source_channel_id}|${c.destination_channel_id}`, c.topic_similarity);
    return m;
  }, [sim]);
  const value = (a: string, b: string) => lookup.get(`${a}|${b}`) ?? lookup.get(`${b}|${a}`) ?? null;
  const axis = sim.status === "success" ? sim.data.channels.map((c) => ({ id: c.channel_id, label: c.channel_name ?? c.channel_id })) : [];
  const related = selected && sim.status === "success"
    ? axis.filter((c) => c.id !== selected).map((c) => ({ ...c, v: value(selected, c.id) })).filter((c) => c.v !== null)
      .sort((a, b) => (b.v ?? 0) - (a.v ?? 0))
    : [];
  const selectedName = axis.find((c) => c.id === selected)?.label;
  const select = (id: string) => setParams(id === selected ? {} : { channel: id });

  return (
    <>
      <PageHeader title="Topic Intelligence" description="Semantic similarity between channel content profiles (video titles and descriptions). It measures what channels publish, not who watches them." />
      {sim.status === "loading" && <Loading label="Loading topic similarity…" />}
      {sim.status === "error" && <ErrorState error={sim.error} onRetry={sim.reload} />}
      {sim.status === "success" && (
        <>
          <section className="rs-strip" aria-label="Topic run">
            <div className="rs-strip__cell"><span>Embedding model</span><strong className="rs-strip__text">{sim.data.model ?? "—"}</strong></div>
            <div className="rs-strip__cell"><span>Channels with a profile</span><strong>{int(sim.data.channels.filter((c) => c.profile_available).length)} / {int(sim.data.channels.length)}</strong></div>
            <div className="rs-strip__cell"><span>Topic clusters</span><strong>{int(sim.data.n_topics)}</strong></div>
            <div className="rs-strip__cell"><span>Run</span><strong className="rs-strip__text">{sim.data.experiment_id ?? "—"}</strong><small>{date(sim.data.created_at)}</small></div>
          </section>
          <Card title="Topic similarity matrix" info="Cosine similarity of channel content profiles (STEP 18). Select a channel to highlight its row and column.">
              <Heatmap axis={axis} value={value} selected={selected} onSelect={select} caption="Topic similarity between research channels" />
            </Card>
          <div className="grid grid--2">
            <Card title={selectedName ? `Most similar to ${selectedName}` : "Related channels"}>
              {!selected ? <EmptyState title="Select a channel in the matrix to list its most similar channels." /> : (
                <ol className="rel-list">
                  {related.map((c) => (
                    <li key={c.id}>
                      <span className="rel-list__name">{c.label}</span>
                      <span className="rel-list__track"><span style={{ width: `${Math.max(0, c.v ?? 0) * 100}%` }} /></span>
                      <span className="rel-list__value">{num(c.v, 3)}</span>
                    </li>
                  ))}
                </ol>
              )}
              {selected && (
                <p className="muted small">
                  <Link to={`/channels?channel=${encodeURIComponent(selected)}`}>Open in Channel Explorer →</Link>
                </p>
              )}
            </Card>
            <Card title="Topic clusters" info={clusters.status === "success" ? clusters.data.note : "Unlabelled KMeans clusters of video text."}>
              {clusters.status === "loading" && <Loading />}
              {clusters.status === "error" && <ErrorState error={clusters.error} />}
              {clusters.status === "success" && (
                <ol className="rel-list">
                  {clusters.data.items.map((t) => (
                    <li key={t.topic_id}>
                      <span className="rel-list__name">{t.label}<small>{t.top_channel_name ? `mostly ${t.top_channel_name}` : ""}</small></span>
                      <span className="rel-list__track"><span style={{ width: `${((t.share ?? 0) / (clusters.data.items[0].share || 1)) * 100}%` }} /></span>
                      <span className="rel-list__value">{pct(t.share)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
            <Card title="Topic coverage" info="Share of each channel's collected videos with usable text for its semantic profile.">
              <TableWrap label="Topic coverage">
                <table className="table table--compact">
                  <thead><tr><th scope="col">Channel</th><th scope="col" className="num">Usable videos</th><th scope="col" className="num">Coverage</th><th scope="col">Profile</th></tr></thead>
                  <tbody>
                    {sim.data.channels.map((c) => (
                      <tr key={c.channel_id}>
                        <td>{c.channel_name ?? c.channel_id}</td>
                        <td className="num">{int(c.usable_videos)}</td>
                        <td className="num">{pct(c.coverage_ratio)}</td>
                        <td>{c.profile_available ? <Badge tone="ok">available</Badge> : <Badge tone="warn">missing</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </Card>
          <p className="muted small">{sim.data.note}</p>
          <Provenance snapshotId={sim.data.snapshot_id} extra={sim.data.experiment_id ? `Topic run ${sim.data.experiment_id}` : undefined} />
        </>
      )}
    </>
  );
}
