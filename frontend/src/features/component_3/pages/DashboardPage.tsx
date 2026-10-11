import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { LineChart, Sparkline } from "../../../components/charts/LineChart";
import { HubNetwork, VennDiagram } from "../../../components/charts/Overlap";
import { ChannelAvatar, colorFor } from "../../../components/common/ChannelAvatar";
import { Icon } from "../../../components/common/Icon";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Card, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { compact, date, int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function duration(sec: number): string {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s2 = sec % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s2).padStart(2, "0")}` : `${m}:${String(s2).padStart(2, "0")}`;
}

function Kpi({ icon, tone, label, value, hint, spark, sparkLabel }: {
  icon: string; tone: string; label: string; value: string; hint?: string; spark?: number[]; sparkLabel?: string;
}) {
  return (
    <div className="kpi">
      <span className={`kpi__icon kpi__icon--${tone}`}><Icon name={icon} size={22} /></span>
      <div className="kpi__body">
        <span className="kpi__label">{label}</span>
        <span className="kpi__value-row">
          <span className="kpi__value">{value}</span>
          {spark && sparkLabel && <Sparkline values={spark} color="var(--kpi-spark)" label={sparkLabel} />}
        </span>
        {hint && <span className="kpi__hint">{hint}</span>}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { snapshotId, experimentId, status } = useResearch();
  const c = { snapshotId, experimentId };
  const [granularity, setGranularity] = useState<"month" | "week">("month");
  const summary = useApi((s) => component3Api.dashboardSummary(c, s), [snapshotId]);
  const channels = useApi((s) => component3Api.dashboardChannels(c, s), [snapshotId]);
  const timeline = useApi((s) => component3Api.viewsTimeline(c, granularity, granularity === "month" ? 12 : 16, s), [snapshotId, granularity]);
  const overlap = useApi((s) => component3Api.overlap(c, s), [snapshotId]);
  const videos = useApi((s) => component3Api.topVideos(c, 5, s), [snapshotId]);
  const topics = useApi((s) => component3Api.topics(c, s), [snapshotId]);
  const bridges = useApi((s) => component3Api.topBridges(c, 6, s), [snapshotId, experimentId]);

  const order = useMemo(() => (channels.status === "success" ? channels.data.items.map((x) => x.channel_id) : []), [channels]);
  const totals = useMemo(() => {
    if (timeline.status !== "success") return null;
    const n = timeline.data.periods.length;
    return {
      views: Array.from({ length: n }, (_, i) => timeline.data.series.reduce((a, s) => a + (s.views[i] ?? 0), 0)),
      videos: Array.from({ length: n }, (_, i) => timeline.data.series.reduce((a, s) => a + s.videos[i], 0)),
    };
  }, [timeline]);

  if (status.status === "success" && status.data.research_data === "missing") {
    return <EmptyState title="No research data yet"><p>Run the collection pipeline and create a research snapshot first.</p></EmptyState>;
  }
  if (summary.status === "error") return <ErrorState error={summary.error} onRetry={summary.reload} />;
  const s = summary.status === "success" ? summary.data : null;
  const top = bridges.status === "success" ? bridges.data.items[0] : undefined;
  const periodLabel = (p: string) => (granularity === "month" ? p.slice(0, 7) : p.slice(5));

  return (
    <>
      <section className="hero">
        <div>
          <p className="hero__greeting">{greeting()} · Component 3 Audience Intelligence</p>
          <h1>Audience Insight Dashboard</h1>
          <p className="page-header__description">Cross-channel audience structure of the approved research channels, from public YouTube data.</p>
        </div>
        {top && (
          <Link className="highlight" to={`/explainability?source=${encodeURIComponent(top.source_channel_id)}&destination=${encodeURIComponent(top.destination_channel_id)}`}>
            <span className="highlight__icon"><Icon name="explain" size={20} /></span>
            <span>
              <span className="highlight__title">Data highlight <span className="highlight__chev" aria-hidden="true">›</span></span>
              <span className="highlight__text">
                Strongest potential audience bridge: <strong>{top.source_channel_name} → {top.destination_channel_name}</strong>
              </span>
              <span className="highlight__meta">score {num(top.audience_bridge_score, 3)} · {int(top.shared_commenters)} shared commenters · provisional formula</span>
            </span>
          </Link>
        )}
      </section>

      {summary.status === "loading" || !s ? <Loading label="Loading dashboard…" /> : (
        <section className="kpi-grid" aria-label="Snapshot totals">
          <Kpi icon="users" tone="red" label="Channels" value={int(s.channels)} hint={`${compact(s.subscribers)} subscribers`} />
          <Kpi icon="play" tone="blue" label="Videos" value={int(s.videos)} hint={`${date(s.first_video).slice(0, 7)} → ${date(s.last_video).slice(0, 7)}`}
            spark={totals?.videos} sparkLabel="Collected videos per period" />
          <Kpi icon="eye" tone="green" label="Views" value={compact(s.views)} hint="collected videos, public counts"
            spark={totals?.views} sparkLabel="Views of collected videos per publish period" />
          <Kpi icon="comment" tone="purple" label="Comments" value={compact(s.collected_comments)} hint={`collected of ${compact(s.public_comments)} public`} />
          <Kpi icon="thumb" tone="orange" label="Unique commenters" value={compact(s.unique_commenters)} hint={`${compact(s.likes)} likes on collected videos`} />
        </section>
      )}

      <div className="grid grid--wide-left">
        <Card title="Views of collected videos by publish date" actions={
          <div className="segmented" role="group" aria-label="Granularity">
            {(["month", "week"] as const).map((g) => (
              <button key={g} type="button" className={granularity === g ? "is-active" : ""} aria-pressed={granularity === g} onClick={() => setGranularity(g)}>
                {g === "month" ? "Monthly" : "Weekly"}
              </button>
            ))}
          </div>}>
          {timeline.status === "loading" && <Loading />}
          {timeline.status === "error" && <ErrorState error={timeline.error} />}
          {timeline.status === "success" && (timeline.data.series.length === 0 ? <EmptyState title="No videos in this period" /> : (
            <>
              <LineChart labels={timeline.data.periods.map(periodLabel)} yLabel="Views"
                summary={`Views of collected videos by publish ${granularity} for the top channels`}
                series={timeline.data.series.slice(0, 6).map((x) => ({ key: x.channel_id, label: x.channel_name ?? x.channel_id, color: colorFor(x.channel_id, order), values: x.views }))} />
              <p className="muted small">{timeline.data.note}</p>
            </>
          ))}
        </Card>
        <Card title="Channel audience overlap">
          {overlap.status === "loading" && <Loading />}
          {overlap.status === "error" && <ErrorState error={overlap.error} />}
          {overlap.status === "success" && (
            <>
              <VennDiagram shared={overlap.data.commenters_on_multiple_channels}
                channels={overlap.data.nodes.map((n) => ({ id: n.channel_id, label: n.channel_name ?? n.channel_id, value: n.unique_commenters, color: colorFor(n.channel_id, order) }))} />
              <ol className="mini-list">
                {overlap.data.edges.slice(0, 3).map((e) => {
                  const nm = (id: string) => overlap.data.nodes.find((n) => n.channel_id === id)?.channel_name ?? id;
                  return <li key={`${e.source_channel_id}-${e.destination_channel_id}`}><span>{nm(e.source_channel_id)} ↔ {nm(e.destination_channel_id)}</span><strong>{int(e.shared_commenters)}</strong></li>;
                })}
              </ol>
              <p className="muted small">Top channels by unique commenters; the centre shows commenters seen on 2+ channels. Layout is illustrative (overlap areas are not to scale); numbers are exact.</p>
            </>
          )}
        </Card>
      </div>

      <div className="grid grid--2">
        <Card title="Channel performance" actions={<Link to="/channels" className="card-link">View all →</Link>}>
          {channels.status === "loading" && <Loading />}
          {channels.status === "error" && <ErrorState error={channels.error} />}
          {channels.status === "success" && (
            <TableWrap label="Channel performance">
              <table className="table table--compact">
                <thead><tr><th scope="col">#</th><th scope="col">Channel</th><th scope="col" className="col-optional">Subscribers</th><th scope="col">Views*</th><th scope="col" className="col-optional">Videos*</th><th scope="col">Commenters</th></tr></thead>
                <tbody>
                  {channels.data.items.slice(0, 8).map((x, i) => (
                    <tr key={x.channel_id}>
                      <td>{i + 1}</td>
                      <td><span className="channel-cell"><ChannelAvatar id={x.channel_id} name={x.channel_name} order={order} size={22} /><Link to={`/channels?channel=${encodeURIComponent(x.channel_id)}`}>{x.channel_name ?? x.channel_id}</Link></span></td>
                      <td className="num col-optional">{compact(x.subscriber_count)}</td>
                      <td className="num">{compact(x.views)}</td>
                      <td className="num col-optional">{int(x.videos)}</td>
                      <td className="num">{int(x.unique_commenters)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
          <p className="muted small">* collected videos only (up to the collection limit per channel).</p>
        </Card>
        <Card title="Top performing content">
          {videos.status === "loading" && <Loading />}
          {videos.status === "error" && <ErrorState error={videos.error} />}
          {videos.status === "success" && (videos.data.items.length === 0 ? <EmptyState title="No view counts available" /> : (
            <ul className="video-list">
              {videos.data.items.map((v) => (
                <li key={v.video_id}>
                  <a href={v.video_url} target="_blank" rel="noreferrer" className="video-thumb">
                    <img src={v.thumbnail_url} alt="" loading="lazy" width={112} height={63} />
                    {v.duration_seconds !== null && <span className="video-thumb__duration">{duration(v.duration_seconds)}</span>}
                  </a>
                  <div className="video-body">
                    <a href={v.video_url} target="_blank" rel="noreferrer" className="video-title">{v.title ?? v.video_id}</a>
                    <span className="video-meta"><ChannelAvatar id={v.channel_id} name={v.channel_name} order={order} size={16} /> {v.channel_name} · {date(v.published_at).slice(0, 10)}</span>
                  </div>
                  <div className="video-stats">
                    <span title="Views"><Icon name="eye" size={14} /> {compact(v.views)}</span>
                    <span title="Likes"><Icon name="thumb" size={14} /> {compact(v.likes)}</span>
                    <span title="Comments"><Icon name="comment" size={14} /> {compact(v.comments)}</span>
                  </div>
                </li>
              ))}
            </ul>
          ))}
        </Card>
      </div>

      <div className="grid grid--3">
        <Card title="Audience overlap network">
          {overlap.status === "loading" && <Loading />}
          {overlap.status === "error" && <ErrorState error={overlap.error} />}
          {overlap.status === "success" && (
            <>
              <HubNetwork
                channels={overlap.data.nodes.map((n) => ({ id: n.channel_id, label: n.channel_name ?? n.channel_id, value: n.unique_commenters, color: colorFor(n.channel_id, order) }))}
                links={overlap.data.edges.map((e) => ({ a: e.source_channel_id, b: e.destination_channel_id, weight: e.shared_commenters }))} />
              <p className="muted small">Most-connected channels by shared commenters (aggregate counts; not audience migration).</p>
            </>
          )}
        </Card>
        <Card title="Content topics">
          {topics.status === "loading" && <Loading />}
          {topics.status === "error" && <ErrorState error={topics.error} />}
          {topics.status === "success" && (
            <>
              <ol className="bar-list">
                {topics.data.items.map((t) => (
                  <li key={t.topic_id}>
                    <span className="bar-list__label">{t.label}<small>{t.top_channel_name ? `mostly ${t.top_channel_name}` : ""}</small></span>
                    <span className="bar-list__track"><span style={{ width: `${(t.share ?? 0) * 100}%` }} /></span>
                    <span className="bar-list__value">{pct(t.share)} · {int(t.videos)} videos</span>
                  </li>
                ))}
              </ol>
              <p className="muted small">{topics.data.note}</p>
            </>
          )}
        </Card>
        <Card title="Top potential audience bridges" actions={<Link to="/bridges" className="card-link">Explore →</Link>}>
          {bridges.status === "loading" && <Loading />}
          {bridges.status === "error" && <ErrorState error={bridges.error} />}
          {bridges.status === "success" && (bridges.data.items.length === 0 ? <EmptyState title="No positive scores" /> : (
            <ol className="bridge-list">
              {bridges.data.items.map((b) => (
                <li key={`${b.source_channel_id}-${b.destination_channel_id}`}>
                  <Link to={`/explainability?source=${encodeURIComponent(b.source_channel_id)}&destination=${encodeURIComponent(b.destination_channel_id)}`}>
                    <ChannelAvatar id={b.source_channel_id} name={b.source_channel_name} order={order} size={24} />
                    <span className="bridge-list__arrow">→</span>
                    <ChannelAvatar id={b.destination_channel_id} name={b.destination_channel_name} order={order} size={24} />
                    <span className="bridge-list__names">{b.source_channel_name} → {b.destination_channel_name}<small>{int(b.shared_commenters)} shared commenters · confidence {num(b.confidence, 2)}</small></span>
                    <span className="bridge-list__score">{num(b.audience_bridge_score, 3)}</span>
                  </Link>
                </li>
              ))}
            </ol>
          ))}
        </Card>
      </div>
      <p className="notice small">{LIMITATIONS}</p>
      <Provenance snapshotId={s?.snapshot_id ?? null} experimentId={bridges.status === "success" ? bridges.data.experiment_id : null} />
    </>
  );
}
