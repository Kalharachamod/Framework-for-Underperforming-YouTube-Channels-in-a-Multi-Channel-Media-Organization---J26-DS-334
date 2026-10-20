/** Analyze Organization extras: live per-channel progress, top-bridge preview and organization comparison.
 * Everything shown comes from the job record or the stored results of a snapshot; nothing is estimated. */
import { ChannelAvatar } from "../../components/common/ChannelAvatar";
import { ErrorState, Loading } from "../../components/common/States";
import { useApi } from "../../hooks/useApi";
import { int, num, pct } from "../../utils/format";
import type { AnalysisJob } from "./analysisApi";
import { component3Api } from "./api";
import type { BridgePairRow, DashboardSummary } from "./types";

/** Channel logos that light up as their comments are collected (from the job's per-channel progress). */
export function ChannelProgressGrid({ job }: { job: AnalysisJob }) {
  const comments = job.steps.find((s) => s.step === "comments");
  const details = (comments?.details ?? {}) as { channels_done?: string[]; channel_now?: string | null };
  const done = new Set(details.channels_done ?? []);
  const allDone = comments?.status === "completed" || job.status === "completed";
  const started = comments && comments.status !== "pending";
  return (
    <div className="az-live" aria-label="Channels">
      <div className="az-live__head">
        <strong>Channels</strong>
        <span className="muted">{allDone ? job.channels.length : done.size} of {job.channels.length} collected</span>
      </div>
      <ul className="az-live__grid">
        {job.channels.map((c) => {
          const state = allDone || done.has(c.channel_id) ? "done" : details.channel_now === c.channel_id ? "now" : "wait";
          const label = state === "done" ? "done" : state === "now" ? "collecting" : started ? "waiting" : "queued";
          return (
            <li key={c.channel_id} className={`az-live__ch is-${state}`} aria-label={`${c.title}: ${label}`}>
              <span className="az-live__logo"><ChannelAvatar id={c.channel_id} name={c.title} size={44} />
                {state === "done" && <span className="az-live__tick" aria-hidden="true">✓</span>}
              </span>
              <span className="az-live__name">{c.title}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** The strongest stored bridge of a snapshot: two logos and the score. */
export function OrgTopBridge({ snapshotId }: { snapshotId: string }) {
  const top = useApi((s) => component3Api.topBridges({ snapshotId }, 1, s), [snapshotId]);
  if (top.status !== "success") return <div className="az-topb az-topb--empty">{top.status === "error" ? "No bridge scores yet" : "Loading top bridge…"}</div>;
  const b = top.data.items[0];
  if (!b || !b.audience_bridge_score) return <div className="az-topb az-topb--empty">No bridge evidence in this sample</div>;
  return (
    <div className="az-topb" title="Strongest stored potential audience bridge (source → destination)">
      <span className="az-topb__kicker">Top bridge</span>
      <span className="az-topb__pair">
        <ChannelAvatar id={b.source_channel_id} name={b.source_channel_name} size={26} />
        <span className="az-topb__name">{b.source_channel_name}</span>
        <span className="az-topb__arrow" aria-hidden="true">→</span>
        <ChannelAvatar id={b.destination_channel_id} name={b.destination_channel_name} size={26} />
        <span className="az-topb__name">{b.destination_channel_name}</span>
      </span>
      <b className="az-topb__score">{num(b.audience_bridge_score, 2)}</b>
    </div>
  );
}

interface OrgStats {
  summary: DashboardSummary;
  pairs: BridgePairRow[];
}

function useOrgStats(snapshotId: string) {
  return useApi(async (s): Promise<OrgStats> => {
    const [summary, pairs] = await Promise.all([component3Api.dashboardSummary({ snapshotId }, s), component3Api.bridgePairs({ snapshotId }, s)]);
    return { summary, pairs: pairs.items };
  }, [snapshotId]);
}

function derive(st: OrgStats) {
  const scored = st.pairs.filter((p) => p.audience_bridge_score !== null);
  const evidence = scored.filter((p) => (p.shared_commenters ?? 0) > 0);
  const channels = new Set(scored.flatMap((p) => [p.source_channel_id, p.destination_channel_id]));
  const connected = new Set(evidence.flatMap((p) => [p.source_channel_id, p.destination_channel_id]));
  const top = [...evidence].sort((a, b) => (b.audience_bridge_score ?? 0) - (a.audience_bridge_score ?? 0)).slice(0, 3);
  const mean = evidence.length ? evidence.reduce((s, p) => s + (p.audience_bridge_score ?? 0), 0) / evidence.length : null;
  return {
    channels: st.summary.channels, videos: st.summary.videos, comments: st.summary.collected_comments,
    commenters: st.summary.unique_commenters, evidenceShare: scored.length ? evidence.length / scored.length : null,
    isolated: [...channels].filter((c) => !connected.has(c)).length, mean, strongest: top[0]?.audience_bridge_score ?? null, top,
  };
}

type Derived = ReturnType<typeof derive>;
const ROWS: { key: keyof Derived; label: string; fmt: (v: number | null) => string; higherIsMore?: boolean }[] = [
  { key: "channels", label: "Channels", fmt: int },
  { key: "videos", label: "Videos collected", fmt: int },
  { key: "comments", label: "Comments collected", fmt: int },
  { key: "commenters", label: "Unique commenters", fmt: int },
  { key: "evidenceShare", label: "Pairs with shared commenters", fmt: (v) => pct(v, 0) },
  { key: "mean", label: "Average bridge score (evidence pairs)", fmt: (v) => num(v, 3) },
  { key: "strongest", label: "Strongest bridge", fmt: (v) => num(v, 3) },
  { key: "isolated", label: "Channels with no bridge", fmt: int },
];

/** Side-by-side comparison of two analysed organizations (stored results of each one's snapshot). */
export function OrgCompare({ a, b, names, onClose }: { a: string; b: string; names: [string, string]; onClose: () => void }) {
  const sa = useOrgStats(a), sb = useOrgStats(b);
  return (
    <section className="az-panel az-cmp" aria-label="Organization comparison">
      <header className="az-panel__head az-panel__head--row">
        <div><h2>{names[0]} vs {names[1]}</h2><p>Stored results of each organization's latest analysis, side by side.</p></div>
        <button type="button" className="az-chip" onClick={onClose}>Close comparison</button>
      </header>
      {(sa.status === "loading" || sb.status === "loading" || sa.status === "idle" || sb.status === "idle") && <Loading variant="table" rows={6} label="Loading both organizations…" />}
      {sa.status === "error" && <ErrorState error={sa.error} onRetry={sa.reload} what={names[0]} />}
      {sb.status === "error" && <ErrorState error={sb.error} onRetry={sb.reload} what={names[1]} />}
      {sa.status === "success" && sb.status === "success" && (() => {
        const da = derive(sa.data), db = derive(sb.data);
        return (
          <>
            <div className="az-cmp__table" role="table" aria-label="Comparison">
              <div className="az-cmp__row az-cmp__row--head" role="row">
                <span role="columnheader">{names[0]}</span><span role="columnheader">Measure</span><span role="columnheader">{names[1]}</span>
              </div>
              {ROWS.map((r) => {
                const va = da[r.key] as number | null, vb = db[r.key] as number | null;
                const max = Math.max(va ?? 0, vb ?? 0) || 1;
                return (
                  <div key={r.key} className="az-cmp__row" role="row">
                    <span className="az-cmp__val az-cmp__val--a" role="cell"><b>{r.fmt(va)}</b><i style={{ width: `${((va ?? 0) / max) * 100}%` }} /></span>
                    <span className="az-cmp__label" role="cell">{r.label}</span>
                    <span className="az-cmp__val az-cmp__val--b" role="cell"><i style={{ width: `${((vb ?? 0) / max) * 100}%` }} /><b>{r.fmt(vb)}</b></span>
                  </div>
                );
              })}
            </div>
            <div className="az-cmp__tops">
              {[da, db].map((d, i) => (
                <div key={names[i]}>
                  <h3>Top bridges · {names[i]}</h3>
                  {d.top.length === 0 ? <p className="muted">No bridge evidence in this sample.</p> : (
                    <ol>
                      {d.top.map((p) => (
                        <li key={`${p.source_channel_id}>${p.destination_channel_id}`}>
                          <ChannelAvatar id={p.source_channel_id} name={p.source_channel_name} size={24} />
                          <span>{p.source_channel_name}</span><span aria-hidden="true">→</span>
                          <ChannelAvatar id={p.destination_channel_id} name={p.destination_channel_name} size={24} />
                          <span>{p.destination_channel_name}</span>
                          <b>{num(p.audience_bridge_score, 3)}</b>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ))}
            </div>
            <p className="muted az-hint">
              Compare with care: the two analyses may use different sample sizes and dates, and scores are relative within each
              source channel. Differences describe the collected public comments, not the organizations' whole audiences.
            </p>
          </>
        );
      })()}
    </section>
  );
}
