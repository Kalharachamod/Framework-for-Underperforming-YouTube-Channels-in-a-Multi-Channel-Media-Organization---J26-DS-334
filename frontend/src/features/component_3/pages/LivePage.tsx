import { useState } from "react";
import { ChannelAvatar } from "../../../components/common/ChannelAvatar";
import { ErrorState, Loading } from "../../../components/common/States";
import { Icon } from "../../../components/common/Icon";
import { Badge, type Tone } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, num, pct } from "../../../utils/format";
import { liveApi, type LiveBridge, type LiveRun } from "../liveApi";

const STATUS_TONE: Record<LiveRun["status"], Tone> = { completed: "ok", running: "warn", failed: "bad" };
const TOP = 12;

function ago(iso: string | null): string {
  if (!iso) return "—";
  const h = Math.round((Date.now() - Date.parse(iso)) / 3_600_000);
  return h < 1 ? "less than an hour ago" : h < 48 ? `${h} hours ago` : `${Math.round(h / 24)} days ago`;
}

/** One pair's score over the nightly runs (simple SVG line, oldest left). */
function Trend({ pair }: { pair: LiveBridge }) {
  const h = useApi((s) => liveApi.history(pair.source_channel_id, pair.destination_channel_id, s),
    [pair.source_channel_id, pair.destination_channel_id]);
  if (h.status === "loading" || h.status === "idle") return <Loading variant="chart" label="Loading trend…" />;
  if (h.status === "error") return <ErrorState error={h.error} onRetry={h.reload} what="Score history" />;
  const pts = h.data.items.filter((p) => p.audience_bridge_score !== null);
  if (pts.length < 2) return <p className="muted lv-trend__empty">The trend appears after two or more nightly runs ({pts.length} so far).</p>;
  const W = 560, H = 150, P = 24;
  const xs = (i: number) => P + (i * (W - 2 * P)) / (pts.length - 1);
  const ys = (v: number) => H - P - v * (H - 2 * P);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${xs(i)},${ys(p.audience_bridge_score as number)}`).join(" ");
  return (
    <figure className="lv-trend">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Bridge score over ${pts.length} nightly runs`}>
        <defs><linearGradient id="lvg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#6366f1" stopOpacity=".35" /><stop offset="1" stopColor="#6366f1" stopOpacity="0" /></linearGradient></defs>
        {[0, 0.5, 1].map((g) => <line key={g} x1={P} x2={W - P} y1={ys(g)} y2={ys(g)} className="lv-trend__grid" />)}
        <path d={`${path} L${xs(pts.length - 1)},${H - P} L${xs(0)},${H - P} Z`} fill="url(#lvg)" />
        <path d={path} className="lv-trend__line" />
        {pts.map((p, i) => <circle key={p.run_id} cx={xs(i)} cy={ys(p.audience_bridge_score as number)} r={3.5} className="lv-trend__dot"><title>{`${date(p.finished_at)}: ${num(p.audience_bridge_score, 3)}`}</title></circle>)}
      </svg>
      <figcaption className="muted">{date(pts[0].finished_at).slice(0, 10)} → {date(pts[pts.length - 1].finished_at).slice(0, 10)} · {pts.length} nightly runs</figcaption>
    </figure>
  );
}

export function LivePage() {
  const bridges = useApi((s) => liveApi.bridges(500, s), []);
  const runs = useApi((s) => liveApi.runs(14, s), []);
  const [picked, setPicked] = useState<string | null>(null);

  const latestRun = runs.status === "success" ? runs.data.items[0] : undefined;
  const notReady = bridges.status === "error" && (bridges.error.code === "not_found" || bridges.error.code === "storage_unavailable");

  return (
    <div className="az lv">
      <section className="az-hero2 lv-hero" aria-label="Live results">
        <div className="az-hero2__text">
          <span className="az-hero2__kicker"><span className="lv-dot" aria-hidden="true" /> Live · updated nightly</span>
          <h1>Live audience bridges</h1>
          <p>Every night the system collects new public YouTube data, recomputes the Audience Bridge Score on a rolling window
            (the same period for every channel) and publishes the results here.</p>
          {bridges.status === "success" && (
            <div className="az-hero2__stats">
              <span><b>{ago(bridges.data.run.finished_at)}</b> last update</span>
              <span><b>{int(bridges.data.run.channels)}</b> channels</span>
              <span><b>{int(bridges.data.run.videos)}</b> videos</span>
              <span><b>{int(bridges.data.run.comments)}</b> comments</span>
            </div>
          )}
        </div>
        {bridges.status === "success" && (
          <div className="lv-hero__meta">
            <span>Run <code>{bridges.data.run.run_id}</code></span>
            <span>Window {date(bridges.data.run.window_start).slice(0, 10)} → {date(bridges.data.run.window_end).slice(0, 10)}</span>
            <span>{bridges.data.pairs_with_evidence} of {bridges.data.pairs} pairs share commenters ({pct(bridges.data.pairs ? bridges.data.pairs_with_evidence / bridges.data.pairs : null, 0)})</span>
          </div>
        )}
      </section>

      {latestRun && latestRun.status === "failed" && (
        <p className="lv-alert" role="alert"><Icon name="status" size={16} /> Last night's run failed: {latestRun.error ?? "unknown error"}. The results below are from the last successful run.</p>
      )}

      {(bridges.status === "loading" || bridges.status === "idle") && <Loading variant="cards" rows={6} label="Loading live results…" />}
      {notReady && (
        <section className="az-panel lv-setup" aria-label="Live results not available yet">
          <header className="az-panel__head"><h2>Live results are not available yet</h2><p>{bridges.status === "error" ? bridges.error.message : ""}</p></header>
          <ol>
            <li>Create the live tables once: <code>python -m shared.database.migrate</code></li>
            <li>In GitHub: <b>Settings → Secrets and variables → Actions</b>, add <code>YOUTUBE_API_KEY</code>, <code>COMMENTER_HASH_SALT</code> and <code>SUPABASE_DB_URL</code></li>
            <li>In GitHub: <b>Actions → Component 3 nightly → Run workflow</b> (or wait for 00:00 Sri Lanka time)</li>
          </ol>
        </section>
      )}
      {bridges.status === "error" && !notReady && <ErrorState error={bridges.error} onRetry={bridges.reload} what="Live results" />}

      {bridges.status === "success" && (() => {
        const top = bridges.data.items.filter((b) => (b.audience_bridge_score ?? 0) > 0).slice(0, TOP);
        const pair = top.find((b) => `${b.source_channel_id}>${b.destination_channel_id}` === picked) ?? top[0];
        return (
          <>
            <div className="lv-grid">
              <section className="az-panel" aria-label="Top live bridges">
                <header className="az-panel__head"><h2>Top bridges right now</h2><p>Strongest potential audience bridges in the current window. Select one to see its trend.</p></header>
                {top.length === 0 ? <p className="muted">No bridge evidence in the current window yet.</p> : (
                  <ol className="lv-bridges">
                    {top.map((b, i) => {
                      const key = `${b.source_channel_id}>${b.destination_channel_id}`;
                      return (
                        <li key={key}>
                          <button type="button" className={pair && key === `${pair.source_channel_id}>${pair.destination_channel_id}` ? "is-on" : ""}
                            onClick={() => setPicked(key)} aria-label={`${b.source_channel_name} to ${b.destination_channel_name}`}>
                            <span className="lv-bridges__rank">{i + 1}</span>
                            <ChannelAvatar id={b.source_channel_id} name={b.source_channel_name} size={30} />
                            <span className="lv-bridges__arrow" aria-hidden="true">→</span>
                            <ChannelAvatar id={b.destination_channel_id} name={b.destination_channel_name} size={30} />
                            <span className="lv-bridges__names"><strong>{b.source_channel_name}</strong><span>to {b.destination_channel_name}</span></span>
                            <span className="lv-bridges__bar"><i style={{ width: `${(b.audience_bridge_score ?? 0) * 100}%` }} /></span>
                            <b className="lv-bridges__score">{num(b.audience_bridge_score, 3)}</b>
                            <small>{int(b.shared_commenters)} shared</small>
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </section>
              <section className="az-panel" aria-label="Trend">
                <header className="az-panel__head"><h2>Trend</h2>{pair && <p>{pair.source_channel_name} → {pair.destination_channel_name}</p>}</header>
                {pair ? <Trend pair={pair} /> : <p className="muted">Select a bridge.</p>}
              </section>
            </div>

            <section className="az-panel" aria-label="Channels in the window">
              <header className="az-panel__head"><h2>Channels in the window</h2><p>Collected public data per channel for the current run.</p></header>
              <div className="lv-channels">
                {bridges.data.channels.map((c) => (
                  <div key={c.channel_id} className="lv-channel">
                    <ChannelAvatar id={c.channel_id} name={c.channel_name} size={36} />
                    <div><strong>{c.channel_name ?? c.channel_id}</strong><span>{int(c.videos)} videos · {int(c.comments)} comments · {int(c.unique_commenters)} commenters</span></div>
                  </div>
                ))}
              </div>
            </section>
          </>
        );
      })()}

      {runs.status === "success" && runs.data.items.length > 0 && (
        <section className="az-panel" aria-label="Nightly runs">
          <header className="az-panel__head"><h2>Nightly runs</h2><p>Each night's run, newest first.</p></header>
          <ul className="lv-runs">
            {runs.data.items.map((r) => (
              <li key={r.run_id}>
                <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                <span>{date(r.started_at)}</span>
                <span className="muted">{r.status === "completed" ? `${int(r.videos)} videos · ${int(r.comments)} comments${r.quota_units ? ` · ${int(r.quota_units)} quota units` : ""}` : r.error ?? ""}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="muted az-hint">Live results are monitoring results on a rolling window of the newest data; the frozen thesis results remain the research snapshots. Scores are potential audience bridges, not audience migration or causality.</p>
    </div>
  );
}
