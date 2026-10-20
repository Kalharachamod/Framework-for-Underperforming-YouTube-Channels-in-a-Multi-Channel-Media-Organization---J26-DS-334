import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowNode } from "../../../components/charts/FlowCanvas";
import { Gauge } from "../../../components/charts/Gauge";
import { ChannelAvatar } from "../../../components/common/ChannelAvatar";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { BridgePairRow, ChannelDetailResponse } from "../types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const compactNum = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);

/** Panel with a title row; the visual inside carries the content. */
function Block({ title, hint, label, action, children, className = "" }: {
  title: string; hint?: string; label?: string; action?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`xblock ${className}`} aria-label={label ?? title}>
      <header className="xblock__head">
        <div><h3>{title}</h3>{hint && <p>{hint}</p>}</div>
        {action}
      </header>
      {children}
    </section>
  );
}

/** Stepped bars from the widest public count to the narrowest engagement count (log-scaled widths). */
function AudienceLadder({ d }: { d: ChannelDetailResponse }) {
  const steps = ([
    ["Public views", d.observed_view_count, "lifetime, public"],
    ["Subscribers", d.observed_subscriber_count, "public, at collection"],
    ["Collected comments", d.comment_count, `${int(d.reply_count)} of them replies`],
    ["Unique commenters", d.unique_commenter_count, "aggregate count"],
    ["Repeat commenters", d.active_commenter_count, "2+ comments"],
  ] as [string, number | null, string][]).filter(([, v]) => v !== null && v > 0) as [string, number, string][];
  const top = Math.log10(Math.max(10, ...steps.map(([, v]) => v)));
  return (
    <ol className="ladder">
      {steps.map(([k, v, note], i) => (
        <li key={k}>
          <span className="ladder__bar" style={{ width: `${Math.max(14, (Math.log10(v + 1) / top) * 100)}%`, opacity: 1 - i * 0.12 }}>
            <strong>{compactNum(v)}</strong>
          </span>
          <span className="ladder__text"><b>{k}</b><small>{note}</small></span>
        </li>
      ))}
    </ol>
  );
}

/** Inbound channels → this channel → outbound channels, as a left-to-right card graph. */
function BridgePosition({ channel, name, inbound, outbound }: { channel: string; name: string; inbound: BridgePairRow[]; outbound: BridgePairRow[] }) {
  const W = 1000, CW = 250, CH = 62, GAP = 14;
  const rows = Math.max(inbound.length, outbound.length, 2);
  const H = rows * (CH + GAP) + 24;
  const col = (n: number) => Array.from({ length: n }, (_, i) => 12 + (H - 24 - (n * (CH + GAP) - GAP)) / 2 + i * (CH + GAP));
  const card = (id: string, label: string, r: BridgePairRow, x: number, y: number, side: "in" | "out"): FlowNode => ({
    id: `${side}:${id}`, x, y, w: CW, h: CH,
    label: side === "in" ? `${label} to ${name}: score ${num(r.audience_bridge_score, 3)}` : `${name} to ${label}: score ${num(r.audience_bridge_score, 3)}`,
    content: (
      <span className="pc">
        <ChannelAvatar id={id} name={label} size={30} />
        <span className="pc__text"><b>{label}</b><small>conf {num(r.confidence_component, 2)} · {int(r.shared_commenters)} shared</small></span>
        <strong className="pc__score">{num(r.audience_bridge_score, 3)}</strong>
      </span>
    ),
  });
  const nodes: FlowNode[] = [
    { id: "me", x: (W - CW) / 2, y: (H - 96) / 2, w: CW, h: 96, tone: "stored", label: `${name}: selected channel`,
      content: (
        <span className="pc pc--me">
          <ChannelAvatar id={channel} name={name} size={44} />
          <span className="pc__text"><b>{name}</b><small>{inbound.length} in · {outbound.length} out shown</small></span>
        </span>
      ) },
    ...col(inbound.length).map((y, i) => card(inbound[i].source_channel_id, inbound[i].source_channel_name ?? inbound[i].source_channel_id, inbound[i], 10, y, "in")),
    ...col(outbound.length).map((y, i) => card(outbound[i].destination_channel_id, outbound[i].destination_channel_name ?? outbound[i].destination_channel_id, outbound[i], W - CW - 10, y, "out")),
  ];
  const edge = (from: string, to: string, r: BridgePairRow): FlowEdge => {
    const s = r.audience_bridge_score ?? 0;
    return { from, to, dir: "right", width: 1.5 + 4 * s, color: s >= 0.6 ? "#1d4ed8" : s >= 0.3 ? "#60a5fa" : "#cbd5e1",
      dashed: (r.confidence_component ?? 0) < 0.5, label: s.toFixed(2), labelAt: from === "me" ? 0.72 : 0.28 };
  };
  const edges = [...inbound.map((r) => edge(`in:${r.source_channel_id}`, "me", r)), ...outbound.map((r) => edge("me", `out:${r.destination_channel_id}`, r))];
  if (inbound.length === 0 && outbound.length === 0) return <EmptyState title="No scored bridge for this channel." />;
  return (
    <>
      <div className="bp-lanes" aria-hidden="true"><span>Inbound · other channel → this channel</span><span>Outbound · this channel → other channel</span></div>
      <FlowCanvas width={W} height={H} nodes={nodes} edges={edges} label={`Bridge position of ${name}`} minScale={0.55} />
      <FlowLegend items={[{ kind: "line", label: "Arrow: direction" }, { kind: "dash", label: "Dashed: confidence below 0.5" },
        { kind: "dot", tone: "strong", label: "Score ≥ 0.6" }, { kind: "dot", tone: "moderate", label: "0.3 – 0.6" }, { kind: "dot", tone: "weak", label: "< 0.3" }]} />
    </>
  );
}

/** The channel in the centre, its most similar channels by content around it. */
function Orbit({ channel, name, rows }: { channel: string; name: string; rows: { key: string; name: string; value: number | null }[] }) {
  const pts = rows.map((r, i) => {
    const a = (-90 + (360 / rows.length) * i) * (Math.PI / 180);
    return { ...r, x: 50 + 36 * Math.cos(a), y: 50 + 38 * Math.sin(a) };
  });
  const vals = rows.map((r) => r.value ?? 0), lo = Math.min(...vals), hi = Math.max(...vals);
  return (
    <div className="orbit" role="img" aria-label={`Most similar channels by content to ${name}: ${rows.map((r) => `${r.name} ${num(r.value, 3)}`).join(", ")}`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <circle cx="50" cy="50" r="37" className="orbit__ring" />
        {pts.map((p) => <line key={p.key} x1="50" y1="50" x2={50 + (p.x - 50) * 0.72} y2={50 + (p.y - 50) * 0.72} className="orbit__spoke"
          style={{ strokeWidth: 0.4 + 1.6 * (hi > lo ? ((p.value ?? 0) - lo) / (hi - lo) : 1) }} />)}
      </svg>
      <span className="orbit__me"><ChannelAvatar id={channel} name={name} size={58} /></span>
      {pts.map((p) => (
        <span key={p.key} className="orbit__pt" style={{ left: `${p.x}%`, top: `${p.y}%` }}>
          <ChannelAvatar id={p.key} name={p.name} size={36} />
          <b>{p.name}</b>
          <small>{num(p.value, 3)}</small>
        </span>
      ))}
    </div>
  );
}

/** One cell per month, shaded by collected videos published that month. */
function MonthStrip({ periods, values }: { periods: string[]; values: number[] }) {
  const max = Math.max(1, ...values);
  const total = values.reduce((a, b) => a + b, 0);
  const peak = values.indexOf(Math.max(...values));
  return (
    <>
      <ol className="months" aria-label="Collected videos per publish month">
        {periods.map((p, i) => (
          <li key={p} title={`${p.slice(0, 7)}: ${values[i]} videos`}>
            <span className="months__cell" style={{ background: values[i] === 0 ? "#f1f5f9" : `rgba(37, 99, 235, ${0.15 + 0.85 * (values[i] / max)})`, color: values[i] / max > 0.5 ? "#fff" : "#1e293b" }}>
              {values[i] || ""}
            </span>
            <small>{MONTHS[Number(p.slice(5, 7)) - 1] ?? p.slice(5, 7)} ’{p.slice(2, 4)}</small>
          </li>
        ))}
      </ol>
      <p className="xnote">{int(total)} collected videos over {periods.length} months{total > 0 ? ` · busiest month ${periods[peak].slice(0, 7)} (${values[peak]})` : ""}.</p>
    </>
  );
}

export function ChannelExplorerPage() {
  const { channels, snapshotId, experimentId } = useResearch();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState("");
  const list = useMemo(() => (channels.status === "success"
    ? [...channels.data.items].sort((a, b) => (b.unique_commenter_count ?? 0) - (a.unique_commenter_count ?? 0)) : []), [channels]);
  // default: the channel with the most unique commenters, so the page never opens empty
  const channel = params.get("channel") ?? list[0]?.channel_id ?? "";
  const maxCommenters = Math.max(1, ...list.map((c) => c.unique_commenter_count ?? 0));
  const order = useMemo(() => list.map((c) => c.channel_id), [list]);

  const on = channel !== "";
  const detail = useApi((s) => component3Api.channel(channel, { snapshotId }, s), [channel, snapshotId], on);
  const allPairs = useApi((s) => component3Api.bridgePairs({ snapshotId, experimentId }, s), [snapshotId, experimentId], on);
  const topicSim = useApi((s) => component3Api.topicSimilarity({ snapshotId }, s), [snapshotId], on);
  const graph = useApi((s) => component3Api.graphSummary({ snapshotId }, s), [snapshotId], on);
  const timeline = useApi((s) => component3Api.viewsTimeline({ snapshotId }, "month", 12, s), [snapshotId], on);
  const pairs = useApi((s) => component3Api.channelPairs(channel, { snapshotId }, 100, 0, s), [channel, snapshotId], on);

  const items = allPairs.status === "success" ? allPairs.data.items : [];
  const outgoing = items.filter((r) => r.source_channel_id === channel && r.audience_bridge_score !== null).sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9));
  const incoming = items.filter((r) => r.destination_channel_id === channel && r.audience_bridge_score !== null)
    .sort((a, b) => (b.audience_bridge_score ?? 0) - (a.audience_bridge_score ?? 0));
  const meanScore = outgoing.length ? outgoing.reduce((a, r) => a + (r.audience_bridge_score ?? 0), 0) / outgoing.length : null;
  // position of this channel's strongest stored outbound score among all sources' strongest scores (display order only)
  const strongestBySource = new Map<string, number>();
  for (const r of items) {
    if (r.audience_bridge_score !== null) strongestBySource.set(r.source_channel_id, Math.max(strongestBySource.get(r.source_channel_id) ?? 0, r.audience_bridge_score));
  }
  const ownStrongest = strongestBySource.get(channel) ?? null;
  const sourceRank = ownStrongest === null ? null : [...strongestBySource.values()].filter((v) => v > ownStrongest).length + 1;
  const topicCoverage = topicSim.status === "success" ? topicSim.data.channels.find((x) => x.channel_id === channel) ?? null : null;
  const connectivity = graph.status === "success" ? graph.data.channel_connectivity.find((c) => c.channel_id === channel) ?? null : null;
  const related = topicSim.status === "success"
    ? topicSim.data.cells.filter((c) => c.source_channel_id === channel && c.topic_similarity !== null)
      .sort((a, b) => (b.topic_similarity ?? 0) - (a.topic_similarity ?? 0)).slice(0, 6)
      .map((c) => ({ key: c.destination_channel_id, value: c.topic_similarity, name: topicSim.data.channels.find((x) => x.channel_id === c.destination_channel_id)?.channel_name ?? c.destination_channel_id }))
    : [];
  const series = timeline.status === "success" ? timeline.data.series.find((x) => x.channel_id === channel) ?? null : null;
  const shown = list.filter((c) => (c.channel_name ?? c.channel_id).toLowerCase().includes(filter.trim().toLowerCase()));
  const shared = pairs.status === "success" ? [...pairs.data.items].sort((a, b) => (b.shared_commenters ?? 0) - (a.shared_commenters ?? 0)) : [];
  const maxShared = Math.max(1, ...shared.map((p) => p.shared_commenters ?? 0));
  const d = detail.status === "success" ? detail.data : null;
  const nm = d?.channel_name ?? channel;

  return (
    <>
      <div className="cx">
        <aside className="cx__list panel" aria-label="Research channels">
          <header className="panel__head"><div><h2>Channels</h2><p>{int(list.length)} in this snapshot · by unique commenters</p></div></header>
          <div className="cx__filter">
            <label htmlFor="explorer-channel-filter" className="sr-only">Filter channels</label>
            <input id="explorer-channel-filter" type="search" placeholder="Filter channels…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
          {channels.status === "loading" && <Loading variant="table" rows={8} />}
          {channels.status === "error" && <ErrorState error={channels.error} onRetry={channels.reload} what="Channels" />}
          <ul>
            {shown.map((c) => (
              <li key={c.channel_id}>
                <button type="button" className={c.channel_id === channel ? "is-on" : ""} aria-pressed={c.channel_id === channel}
                  onClick={() => setParams({ channel: c.channel_id })}>
                  <ChannelAvatar id={c.channel_id} name={c.channel_name} order={order} size={26} />
                  <span className="cx__name">{c.channel_name ?? c.channel_id}</span>
                  <span className="cx__count">{int(c.unique_commenter_count)}</span>
                  <span className="cx__bar" aria-hidden="true"><i style={{ width: `${((c.unique_commenter_count ?? 0) / maxCommenters) * 100}%` }} /></span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="cx__main">
          {!on && channels.status === "success" && <EmptyState title="No research channel in this snapshot." />}
          {detail.status === "loading" && <Loading variant="cards" rows={4} label="Loading channel…" />}
          {detail.status === "error" && <ErrorState error={detail.error} onRetry={detail.reload} what="Channel" />}
          {d && (
            <>
              <section className="xhero" aria-label="Channel">
                <ChannelAvatar id={d.channel_id} name={d.channel_name} order={order} size={76} />
                <div className="xhero__id">
                  <h1>{nm}</h1>
                  <p><code>{d.channel_id}</code></p>
                  <ul className="xhero__tags">
                    <li>Created {date(d.published_at).slice(0, 10)}</li>
                    <li>{compactNum(d.observed_view_count)} public views</li>
                    <li>{int(d.observed_api_video_count)} public videos</li>
                    <li><Badge tone={d.features_status === "available" ? "ok" : "neutral"}>Features {d.features_status}</Badge></li>
                  </ul>
                </div>
                <section className="xhero__facts" aria-label="Research profile">
                  <div><strong>{connectivity ? int(connectivity.connected_channels) : "—"}</strong><span>channels share commenters</span></div>
                  <div><strong>{num(meanScore, 3)}</strong><span>mean outbound score</span></div>
                  <div><strong>{sourceRank === null ? "—" : `#${sourceRank}`}</strong><span>of {strongestBySource.size} by strongest bridge</span></div>
                </section>
              </section>

              <div className="xgrid xgrid--2">
                <Block title="Audience ladder" hint="Public reach down to repeat commenters. Widths on a log scale.">
                  <AudienceLadder d={d} />
                </Block>
                <Block title="Data coverage" hint="How much of this channel the research data covers.">
                  <div className="gauges">
                    <Gauge value={d.collection_coverage} label="Videos collected" caption={`${int(d.stored_video_count)} of ${int(d.observed_api_video_count)} public`} />
                    <Gauge value={topicCoverage ? topicCoverage.coverage_ratio : null} label="Topic profile" caption={topicCoverage?.profile_available ? "videos with usable text" : "not available"} />
                  </div>
                  <ul className="xchips">
                    <li><b>{num(d.avg_comments_per_video, 1)}</b> comments per video</li>
                    <li><b>{d.active_days === null ? "—" : int(d.active_days)}</b> active comment days</li>
                    <li><b>{d.first_interaction_at ? date(d.first_interaction_at).slice(0, 10) : "—"}</b> first comment</li>
                    <li><b>{d.last_interaction_at ? date(d.last_interaction_at).slice(0, 10) : "—"}</b> last comment</li>
                  </ul>
                </Block>
              </div>

              <Block title="Bridge position" hint="Potential audience bridges into and out of this channel (stored scores). Each card is one stored directed bridge."
                action={<Link to={`/bridges?source=${encodeURIComponent(channel)}`} className="card-link">Open bridge graph</Link>}>
                {allPairs.status === "loading" && <Loading variant="graph" label="Loading bridges…" />}
                {allPairs.status === "error" && <ErrorState error={allPairs.error} onRetry={allPairs.reload} what="Bridge scores" />}
                {allPairs.status === "success" && <BridgePosition channel={channel} name={nm} inbound={incoming.slice(0, 5)} outbound={outgoing.slice(0, 5)} />}
              </Block>

              <div className="xgrid xgrid--2">
                <Block title="Content neighbours" hint="Channels whose video text is most similar (topic similarity, symmetric).">
                  {topicSim.status === "loading" && <Loading variant="chart" />}
                  {topicSim.status === "error" && <ErrorState error={topicSim.error} onRetry={topicSim.reload} what="Topic similarity" />}
                  {topicSim.status === "success" && (related.length === 0 ? <EmptyState title="No topic profile for this channel." /> : <Orbit channel={channel} name={nm} rows={related} />)}
                </Block>
                <Block title="Publishing rhythm" hint="Collected videos by publish month (last 12 months).">
                  {timeline.status === "loading" && <Loading variant="chart" />}
                  {timeline.status === "error" && <ErrorState error={timeline.error} onRetry={timeline.reload} what="Timeline" />}
                  {timeline.status === "success" && (!series ? <EmptyState title="No collected video in the last 12 publish months." /> : <MonthStrip periods={timeline.data.periods} values={series.videos} />)}
                </Block>
              </div>

              <Block title="Shared commenters" hint="Other research channels with at least one commenter in common. Bubble size: shared commenters." label="Channels sharing commenters">
                {pairs.status === "loading" && <Loading variant="cards" rows={6} />}
                {pairs.status === "error" && <ErrorState error={pairs.error} onRetry={pairs.reload} what="Shared commenters" />}
                {pairs.status === "success" && (shared.length === 0 ? (
                  <EmptyState title="No shared commenters"><p>No commenter of this channel was observed on another research channel.</p></EmptyState>
                ) : (
                  <>
                    <ul className="bubbles">
                      {shared.map((p) => {
                        const size = 64 + 76 * Math.sqrt((p.shared_commenters ?? 0) / maxShared);
                        return (
                          <li key={p.destination_channel_id}>
                            <Link to={`/channels?channel=${encodeURIComponent(p.destination_channel_id)}`} className="bubble"
                              title={`Jaccard ${num(p.jaccard_similarity, 4)}`}>
                              <span className="bubble__disc" style={{ width: size, height: size }}>
                                <ChannelAvatar id={p.destination_channel_id} name={p.destination_channel_name} size={Math.round(size * 0.42)} />
                                <strong>{int(p.shared_commenters)}</strong>
                              </span>
                              <b>{p.destination_channel_name ?? p.destination_channel_id}</b>
                              <small>{pct(p.directional_overlap_source_to_destination, 1)} of this channel's commenters</small>
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                    <p className="xnote">{pairs.data.note}</p>
                  </>
                ))}
              </Block>
              <Provenance snapshotId={d.snapshot_id} extra={d.as_of ? `features as of ${date(d.as_of)}` : undefined} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
