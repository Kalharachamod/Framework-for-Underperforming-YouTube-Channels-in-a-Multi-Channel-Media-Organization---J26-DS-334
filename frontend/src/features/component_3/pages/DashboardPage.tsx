import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AudienceRing, MiniArea } from "../../../components/charts/AudienceRing";
import { CountUp } from "../../../components/common/CountUp";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { compact, date, int, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";

type Sort = "views" | "likes" | "comments";

/** Editorial section: number and title on the left, content on the right. */
function Section({ n, title, lead, children, aside }: { n: string; title: string; lead?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="ed-section" aria-label={title}>
      <header className="ed-section__head">
        <span className="ed-section__n">{n}</span>
        <h2>{title}</h2>
        {lead && <p>{lead}</p>}
        {aside}
      </header>
      <div className="ed-section__body">{children}</div>
    </section>
  );
}

function Toggle<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="ed-toggle" role="tablist" aria-label={label}>
      {options.map(([k, l]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} className={value === k ? "is-active" : ""} onClick={() => onChange(k)}>{l}</button>
      ))}
    </div>
  );
}

function Figure({ label, value, format, hint }: { label: string; value: number | null; format: (v: number | null) => string; hint?: string }) {
  return (
    <div className="ed-figure">
      <span className="ed-figure__label">{label}</span>
      <span className="ed-figure__value"><CountUp value={value} format={format} /></span>
      {hint && <span className="ed-figure__hint">{hint}</span>}
    </div>
  );
}

export function DashboardPage() {
  const { snapshotId, experimentId, status } = useResearch();
  const c = { snapshotId, experimentId };
  const [granularity, setGranularity] = useState<"month" | "week">("month");
  const [sort, setSort] = useState<Sort>("views");
  const summary = useApi((s) => component3Api.dashboardSummary(c, s), [snapshotId]);
  const channels = useApi((s) => component3Api.dashboardChannels(c, s), [snapshotId]);
  const timeline = useApi((s) => component3Api.viewsTimeline(c, granularity, granularity === "month" ? 12 : 16, s), [snapshotId, granularity]);
  const overlap = useApi((s) => component3Api.overlap(c, s), [snapshotId]);
  const videos = useApi((s) => component3Api.topVideos(c, 4, s, sort), [snapshotId, sort]);
  const topics = useApi((s) => component3Api.topics(c, s), [snapshotId]);
  const bridges = useApi((s) => component3Api.topBridges(c, 6, s), [snapshotId, experimentId]);

  const maxCommenters = useMemo(() => (channels.status === "success" ? Math.max(1, ...channels.data.items.map((x) => x.unique_commenters)) : 1), [channels]);

  if (status.status === "success" && status.data.research_data === "missing") {
    return <EmptyState title="No research data yet"><p>Run the collection pipeline and create a research snapshot first.</p></EmptyState>;
  }
  if (summary.status === "error") return <ErrorState error={summary.error} onRetry={summary.reload} />;
  const s = summary.status === "success" ? summary.data : null;
  const shared = overlap.status === "success" ? overlap.data.commenters_on_multiple_channels : null;
  const lead = bridges.status === "success" ? bridges.data.items[0] : undefined;
  const rest = bridges.status === "success" ? bridges.data.items.slice(1) : [];
  const xplLink = (a: string, b: string) => `/explainability?source=${encodeURIComponent(a)}&destination=${encodeURIComponent(b)}`;

  return (
    <div className="ed">
      <header className="ed-mast">
        <p className="ed-mast__eyebrow">
          Audience intelligence{s && <> · Snapshot <span className="mono">{s.snapshot_id}</span>{s.extracted_at && <> · {date(s.extracted_at).slice(0, 10)}</>}</>}
        </p>
        <h1 className="ed-mast__title">
          {shared !== null && s ? (
            <><em>{int(shared)}</em> commenters appear on more than one channel.</>
          ) : "Cross-channel audience intelligence."}
        </h1>
        {shared !== null && s && s.unique_commenters > 0 && (
          <p className="ed-mast__sub">That is {pct(shared / s.unique_commenters, 1)} of {int(s.unique_commenters)} commenters across {int(s.channels)} channels. These shared audiences are where potential bridges between channels form.</p>
        )}
      </header>

      {summary.status === "loading" || !s ? <Loading label="Loading dashboard…" /> : (
        <section className="ed-ledger" aria-label="Snapshot totals">
          <Figure label="Channels" value={s.channels} format={int} hint={`${compact(s.subscribers)} subscribers`} />
          <Figure label="Videos" value={s.videos} format={int} hint={`${date(s.first_video).slice(0, 7)} – ${date(s.last_video).slice(0, 7)}`} />
          <Figure label="Views" value={s.views} format={compact} hint="collected videos" />
          <Figure label="Comments" value={s.collected_comments} format={compact} hint={`of ${compact(s.public_comments)} public`} />
          <Figure label="Commenters" value={s.unique_commenters} format={compact} hint={`${compact(s.likes)} likes`} />
        </section>
      )}

      <Section n="01" title="Audience network" lead="Each curve joins two channels that share commenters; thicker means more. Hollow points share none. Hover or focus a channel to isolate it.">
        <div className="ed-network">
          <div className="ed-network__ring">
            {overlap.status === "loading" && <Loading />}
            {overlap.status === "error" && <ErrorState error={overlap.error} />}
            {overlap.status === "success" && (
              <AudienceRing
                nodes={overlap.data.nodes.map((n) => ({ id: n.channel_id, label: n.channel_name ?? n.channel_id, value: n.unique_commenters }))}
                edges={overlap.data.edges.map((e) => ({ a: e.source_channel_id, b: e.destination_channel_id, weight: e.shared_commenters }))}
                accentPair={lead ? [lead.source_channel_id, lead.destination_channel_id] : undefined}
                centerValue={int(overlap.data.commenters_on_multiple_channels)} centerLabel="on 2+ channels" />
            )}
          </div>
          <aside className="ed-bridges" aria-label="Potential audience bridges">
            <p className="ed-kicker">Strongest potential bridge</p>
            {bridges.status === "loading" && <Loading />}
            {bridges.status === "error" && <ErrorState error={bridges.error} />}
            {bridges.status === "success" && !lead && <p className="muted">No positive scores in this experiment.</p>}
            {lead && (
              <Link to={xplLink(lead.source_channel_id, lead.destination_channel_id)} className="ed-lead">
                <span className="ed-lead__pair">{lead.source_channel_name} → {lead.destination_channel_name}</span>
                <span className="ed-lead__score">{num(lead.audience_bridge_score, 3)}</span>
                <span className="ed-lead__meta">Audience Bridge Score · {int(lead.shared_commenters)} shared commenters</span>
              </Link>
            )}
            {rest.length > 0 && (
              <ol className="ed-list" start={2}>
                {rest.map((b, i) => (
                  <li key={`${b.source_channel_id}-${b.destination_channel_id}`}>
                    <Link to={xplLink(b.source_channel_id, b.destination_channel_id)}>
                      <span className="ed-list__n">{String(i + 2).padStart(2, "0")}</span>
                      <span className="ed-list__pair">{b.source_channel_name} → {b.destination_channel_name}</span>
                      <span className="ed-list__score">{num(b.audience_bridge_score, 3)}</span>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
            <Link to="/bridges" className="ed-more">All bridges →</Link>
            <p className="ed-note">Provisional scores: an audience-affinity ranking signal, not observed movement.</p>
          </aside>
        </div>
      </Section>

      <Section n="02" title="Views over time" lead={timeline.status === "success" ? timeline.data.note : "Views of collected videos by publish period."}
        aside={<Toggle label="Granularity" value={granularity} options={[["month", "Monthly"], ["week", "Weekly"]]} onChange={setGranularity} />}>
        {timeline.status === "loading" && <Loading />}
        {timeline.status === "error" && <ErrorState error={timeline.error} />}
        {timeline.status === "success" && (timeline.data.series.length === 0 ? <EmptyState title="No videos in this period" /> : (
          <>
            <div className="ed-multiples">
              {timeline.data.series.slice(0, 8).map((x) => (
                <div key={x.channel_id} className="ed-multiple">
                  <span className="ed-multiple__name">{x.channel_name ?? x.channel_id}</span>
                  <span className="ed-multiple__value">{compact(x.views.reduce<number>((a, v) => a + (v ?? 0), 0))}</span>
                  <MiniArea values={x.views} label={`Views of ${x.channel_name} by publish ${granularity}`} />
                  <span className="ed-multiple__axis"><span>{timeline.data.periods[0]?.slice(0, 7)}</span><span>{timeline.data.periods.at(-1)?.slice(0, 7)}</span></span>
                </div>
              ))}
            </div>
            <p className="ed-note">Each panel uses its own vertical scale, starting at zero.</p>
          </>
        ))}
      </Section>

      <Section n="03" title="Channels" lead="Views cover collected videos only (up to 50 per channel); subscribers are public counts at collection."
        aside={<Link to="/channels" className="ed-more">All channels →</Link>}>
        {channels.status === "loading" && <Loading />}
        {channels.status === "error" && <ErrorState error={channels.error} />}
        {channels.status === "success" && (
          <TableWrap label="Channel performance">
            <table className="ed-table">
              <thead><tr><th scope="col">Channel</th><th scope="col" className="num">Subscribers</th><th scope="col" className="num">Views</th><th scope="col" className="num col-optional">Videos</th><th scope="col">Commenters</th></tr></thead>
              <tbody>
                {channels.data.items.slice(0, 10).map((x) => (
                  <tr key={x.channel_id}>
                    <td><Link to={`/channels?channel=${encodeURIComponent(x.channel_id)}`}>{x.channel_name ?? x.channel_id}</Link></td>
                    <td className="num">{compact(x.subscriber_count)}</td>
                    <td className="num">{compact(x.views)}</td>
                    <td className="num col-optional">{int(x.videos)}</td>
                    <td><span className="ed-bar"><span className="ed-bar__track"><span style={{ width: `${(x.unique_commenters / maxCommenters) * 100}%` }} /></span><span className="ed-bar__value">{int(x.unique_commenters)}</span></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Section>

      <Section n="04" title="Most watched" lead="Collected videos ranked by public counts observed at collection."
        aside={<Toggle label="Rank videos by" value={sort} options={[["views", "Views"], ["likes", "Likes"], ["comments", "Comments"]]} onChange={setSort} />}>
        {videos.status === "loading" && <Loading />}
        {videos.status === "error" && <ErrorState error={videos.error} />}
        {videos.status === "success" && (videos.data.items.length === 0 ? <EmptyState title="No public counts available" /> : (
          <ol className="ed-videos">
            {videos.data.items.map((v, i) => (
              <li key={v.video_id}>
                <a href={v.video_url} target="_blank" rel="noreferrer">
                  <span className="ed-videos__thumb"><img src={v.thumbnail_url} alt="" loading="lazy" width={320} height={180} /><span className="ed-videos__n">{String(i + 1).padStart(2, "0")}</span></span>
                  <span className="ed-videos__title">{v.title ?? v.video_id}</span>
                  <span className="ed-videos__meta">{v.channel_name} · {date(v.published_at).slice(0, 10)}</span>
                  <span className="ed-videos__stats">
                    <span className={sort === "views" ? "is-key" : ""}>{compact(v.views)} views</span>
                    <span className={sort === "likes" ? "is-key" : ""}>{compact(v.likes)} likes</span>
                    <span className={sort === "comments" ? "is-key" : ""}>{compact(v.comments)} comments</span>
                  </span>
                </a>
              </li>
            ))}
          </ol>
        ))}
      </Section>

      <Section n="05" title="Content topics" lead={topics.status === "success" ? topics.data.note : "Unlabelled topic clusters of video text."}>
        {topics.status === "loading" && <Loading />}
        {topics.status === "error" && <ErrorState error={topics.error} />}
        {topics.status === "success" && (
          <div className="ed-topics">
            <div className="ed-strip" role="img" aria-label={`Topic shares: ${topics.data.items.map((t) => `${t.label} ${pct(t.share)}`).join(", ")}`}>
              {topics.data.items.map((t, i) => (
                <span key={t.topic_id} style={{ flexGrow: t.share ?? 0, opacity: 1 - Math.min(0.8, i * 0.09) }} className={i === 0 ? "is-first" : ""} title={`${t.label}: ${pct(t.share)}`} />
              ))}
            </div>
            <ol className="ed-topic-list">
              {topics.data.items.slice(0, 8).map((t) => (
                <li key={t.topic_id}>
                  <span className="ed-topic-list__share">{pct(t.share)}</span>
                  <span className="ed-topic-list__label">{t.label}</span>
                  <span className="ed-topic-list__meta">{t.top_channel_name ? `mostly ${t.top_channel_name}` : ""}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Section>

      <footer className="ed-foot">
        <p>{LIMITATIONS}</p>
        <Provenance snapshotId={s?.snapshot_id ?? null} experimentId={bridges.status === "success" ? bridges.data.experiment_id : null} />
      </footer>
    </div>
  );
}
