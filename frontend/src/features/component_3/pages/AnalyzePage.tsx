import { useCallback, useContext, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChannelAvatar, ChannelIconContext } from "../../../components/common/ChannelAvatar";
import { ErrorState, Loading } from "../../../components/common/States";
import { Icon } from "../../../components/common/Icon";
import { Badge, Card, Notice, type Tone } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { ApiError, describeError } from "../../../services/apiClient";
import { compact, date, int } from "../../../utils/format";
import { analysisApi, type AnalysisJob, type Candidate, type DiscoveryResponse, type JobStep } from "../analysisApi";
import { ChannelProgressGrid, OrgCompare, OrgTopBridge } from "../AnalyzeExtras";
import { CompleteAnalysisButton } from "../QuickAnalysis";
import { useResearch } from "../ResearchContext";

const POLL_MS = 2000;
const REGIONS = [
  { value: "LK", label: "Sri Lanka" },
  { value: "IN", label: "India" },
  { value: "", label: "Any region" },
];
const SUGGESTIONS = ["Sirasa", "Hiru", "Swarnavahini", "ITN"];
const ORG_COLORS = ["#4f46e5", "#0d9488", "#2563eb", "#e11d48", "#7c3aed", "#0284c7"];
/** Stable colour per organization (FNV-1a hash of the name). */
const orgColor = (name: string) => {
  let h = 2166136261;
  for (const ch of name) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return ORG_COLORS[h % ORG_COLORS.length];
};
const titleCase = (s: string) => s.replace(/\b\w/g, (c) => c.toUpperCase());

interface OrgSummary { name: string; latest: AnalysisJob; quick: AnalysisJob | null; complete: AnalysisJob | null }

/** One entry per organization: its latest quick analysis and the completion of that analysis' snapshot. */
function groupByOrganization(jobs: AnalysisJob[]): OrgSummary[] {
  const by = new Map<string, AnalysisJob[]>();
  for (const j of jobs) {
    const key = j.organization.trim().toLowerCase();
    by.set(key, [...(by.get(key) ?? []), j]);
  }
  return [...by.entries()].map(([name, list]) => {
    const sorted = [...list].sort((a, b) => b.created_at.localeCompare(a.created_at));
    const quick = sorted.find((j) => j.kind !== "complete") ?? null;
    const sid = quick?.result?.snapshot_id ?? null;
    const complete = sorted.find((j) => j.kind === "complete" && j.status === "completed" && (!sid || j.snapshot_id === sid)) ?? null;
    return { name, latest: sorted[0], quick, complete };
  }).sort((a, b) => b.latest.created_at.localeCompare(a.latest.created_at));
}

const CONFIDENCE_TONE: Record<Candidate["confidence"], Tone> = { high: "ok", medium: "warn", low: "neutral" };
const JOB_TONE: Record<AnalysisJob["status"], Tone> = {
  queued: "neutral", running: "warn", completed: "ok", failed: "bad", interrupted: "bad",
};

function stepDetail(s: JobStep): string | null {
  const d = s.details;
  if (s.step === "comments" && typeof d.videos_total === "number") {
    const done = typeof d.videos_done === "number" ? d.videos_done : d.videos_total;
    const comments = typeof d.collected === "number" ? d.collected : d.comments;
    return `${int(done as number)} of ${int(d.videos_total)} videos${typeof comments === "number" ? ` · ${int(comments)} comments` : ""}`;
  }
  if (s.step === "videos" && typeof d.collected === "number") return `${int(d.collected)} videos`;
  if (s.step === "channels" && typeof d.collected === "number") return `${int(d.collected)} of ${int(d.requested as number)} channels`;
  if (s.step === "snapshot" && typeof d.snapshot_id === "string") return d.snapshot_id;
  if (s.step === "audience_bridge" && typeof d.scored === "number") return `${int(d.scored)} channel pairs scored`;
  if (typeof d.error === "string") return d.error;
  if (typeof d.reason === "string") return d.reason;
  return null;
}

function elapsed(from: string | null, to: string | null): string {
  if (!from) return "";
  const s = Math.max(0, Math.round(((to ? Date.parse(to) : Date.now()) - Date.parse(from)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Live progress of one analysis job. */
function JobProgress({ job, onOpen, onReset }: { job: AnalysisJob; onOpen: (snapshotId: string, page?: string) => void; onReset: () => void }) {
  const done = job.steps.filter((s) => ["completed", "skipped"].includes(s.status)).length;
  const share = job.status === "completed" ? 1 : done / Math.max(1, job.steps.length);
  const active = job.status === "running" || job.status === "queued";
  const rows = job.result?.rows;
  const completing = job.kind === "complete";
  const snapshot = job.result?.snapshot_id ?? job.snapshot_id ?? null;
  return (
    <Card title={`${completing ? "Completing analysis" : "Analysis"}: ${job.organization}`}
      actions={<Badge tone={JOB_TONE[job.status]}>{job.status === "running" ? "Running" : job.status[0].toUpperCase() + job.status.slice(1)}</Badge>}>
      <div className="az-progress" role="progressbar" aria-label="Analysis progress" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(share * 100)}>
        <span style={{ width: `${Math.round(share * 100)}%` }} className={job.status === "failed" ? "is-bad" : ""} />
      </div>
      <p className="muted az-progress__meta">
        {completing ? "HGT, node2vec and evaluation" : `${job.channels.length} channels`} · {Math.round(share * 100)}% · {elapsed(job.started_at, active ? null : job.finished_at)}
        {active && " · this page updates automatically"}
      </p>
      {!completing && job.channels.length > 0 && <ChannelProgressGrid job={job} />}
      <ol className="az-steps">
        {job.steps.map((s) => (
          <li key={s.step} className={`az-step is-${s.status}`}>
            <span className="az-step__icon" aria-hidden="true">
              {s.status === "completed" ? "✓" : s.status === "failed" ? "✕" : s.status === "running" ? "" : s.status === "skipped" ? "–" : "•"}
            </span>
            <span className="az-step__label">{s.label}</span>
            <span className="az-step__detail">{stepDetail(s) ?? (s.status === "running" ? "working…" : "")}</span>
          </li>
        ))}
      </ol>
      {job.status === "failed" || job.status === "interrupted" ? (
        <div className="az-result az-result--bad" role="alert">
          <strong>The analysis did not finish.</strong>
          <p>{job.error}</p>
          <button type="button" className="button" onClick={onReset}>Start again</button>
        </div>
      ) : job.status === "completed" && completing && snapshot ? (
        <div className="az-result">
          <strong>The analysis is complete.</strong>
          <p className="muted">HGT, the node2vec baseline and the evaluation are now available for snapshot <code>{snapshot}</code>.</p>
          <div className="az-actions">
            <button type="button" className="button button--primary" onClick={() => onOpen(snapshot, "/evaluation")}>Open evaluation</button>
            <button type="button" className="button" onClick={onReset}>Analyze another organization</button>
          </div>
        </div>
      ) : job.status === "completed" && job.result?.snapshot_id ? (
        <div className="az-result">
          <div className="az-result__stats">
            <span><strong>{int(rows?.channels)}</strong> channels</span>
            <span><strong>{int(rows?.videos)}</strong> videos</span>
            <span><strong>{int(rows?.comments)}</strong> comments</span>
            <span><strong>{int(job.result.quota_units)}</strong> quota units</span>
          </div>
          <p className="muted">Snapshot <code>{job.result.snapshot_id}</code> · scoring <code>{job.result.experiment_id ?? "—"}</code></p>
          <div className="az-actions">
            <button type="button" className="button button--primary" onClick={() => onOpen(job.result!.snapshot_id!)}>Open results</button>
            <CompleteAnalysisButton snapshotId={job.result.snapshot_id} label="Complete analysis (HGT, node2vec, evaluation)" />
            <button type="button" className="button" onClick={onReset}>Analyze another organization</button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export function AnalyzePage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const linkedJob = params.get("job");
  const { status, setSnapshotId } = useResearch();
  const config = useApi((s) => analysisApi.config(s), []);
  const history = useApi((s) => analysisApi.jobs(s), []);

  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("LK");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [found, setFound] = useState<DiscoveryResponse | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const baseIcons = useContext(ChannelIconContext);
  const reloadHistory = history.reload;
  const reloadStatus = status.reload;
  const cfg = config.status === "success" ? config.data : null;
  const min = cfg?.min_channels ?? 2;
  const max = cfg?.max_channels ?? 25;

  const stopPolling = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  }, []);

  const follow = useCallback((jobId: string) => {
    stopPolling();
    const tick = () => {
      analysisApi.job(jobId).then((j) => {
        setJob(j);
        if (!["queued", "running"].includes(j.status)) {
          stopPolling();
          reloadHistory();
          if (j.status === "completed") reloadStatus(); // the new snapshot appears in the selector
        }
      }).catch(() => undefined); // a missed poll is retried on the next tick
    };
    tick();
    timer.current = setInterval(tick, POLL_MS);
  }, [stopPolling, reloadHistory, reloadStatus]);

  useEffect(() => stopPolling, [stopPolling]);
  // follow a job linked from another page (?job=), or reattach to one that is still running
  useEffect(() => {
    if (job) return;
    if (linkedJob) follow(linkedJob);
    else if (cfg?.active_job_id) follow(cfg.active_job_id);
  }, [cfg?.active_job_id, linkedJob, job, follow]);

  const search = async (e: FormEvent) => {
    e.preventDefault();
    const name = query.trim();
    if (name.length < 2) return;
    setSearching(true);
    setSearchError(null);
    setFound(null);
    try {
      let res: DiscoveryResponse;
      try {
        res = await analysisApi.saved(name);            // an earlier search: free, no YouTube quota
      } catch {
        res = await analysisApi.discover(name, region); // nothing saved (or unreadable): search YouTube
      }
      setFound(res);
      setSelected(new Set(res.candidates.filter((c) => c.confidence === "high").map((c) => c.channel_id)));
    } catch (err) {
      setSearchError(describeError(err));
    } finally {
      setSearching(false);
    }
  };

  const pick = (level: "high" | "medium" | "none") => {
    if (!found) return;
    const keep = level === "high" ? ["high"] : level === "medium" ? ["high", "medium"] : [];
    setSelected(new Set(found.candidates.filter((c) => keep.includes(c.confidence)).map((c) => c.channel_id)));
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const analyze = async () => {
    if (!found) return;
    setStarting(true);
    setStartError(null);
    try {
      const channels = found.candidates.filter((c) => selected.has(c.channel_id)).map((c) => ({ channel_id: c.channel_id, title: c.title }));
      const started = await analysisApi.start(found.organization, channels);
      setJob(started);
      follow(started.job_id);
    } catch (err) {
      setStartError(err instanceof ApiError && err.code === "conflict"
        ? "Another analysis is already running. Wait for it to finish, then try again."
        : describeError(err));
    } finally {
      setStarting(false);
    }
  };

  const open = (snapshotId: string, page = "/dashboard") => {
    setSnapshotId(snapshotId);
    navigate(page);
  };

  const refresh = async () => {
    if (!found) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await analysisApi.discover(found.organization, region);
      setFound(res);
      setSelected(new Set(res.candidates.filter((c) => c.confidence === "high").map((c) => c.channel_id)));
    } catch (err) {
      setSearchError(describeError(err));
    } finally {
      setSearching(false);
    }
  };

  const reset = () => {
    stopPolling();
    if (linkedJob) setParams({});
    setJob(null);
    setFound(null);
    setSelected(new Set());
    setQuery("");
  };

  const count = selected.size;
  const tooFew = count < min;
  const tooMany = count > max;
  const minutes = useMemo(() => Math.max(2, Math.round(count * 0.4 + 2)), [count]);
  const running = job !== null && ["queued", "running"].includes(job.status);
  const orgs = useMemo(() => groupByOrganization((history.status === "success" ? history.data.items : []).filter((j) => j.job_id !== job?.job_id)),
    [history, job?.job_id]);
  const step = job ? 3 : found ? 2 : 1;
  const enabled = Boolean(cfg?.enabled);
  // real channel icons: stored icons for analysed channels + the thumbnails returned by the current search
  const icons = useMemo(() => {
    const m = new Map(baseIcons);
    for (const c of found?.candidates ?? []) if (c.icon_url) m.set(c.channel_id, c.icon_url);
    return m;
  }, [baseIcons, found]);
  const cloud = useMemo(() => {
    // round-robin over organizations, so every analysed organization shows up in the hero
    const lists = orgs.map((o) => (o.quick?.channels ?? []).map((c) => c.channel_id).filter((id) => icons.has(id)));
    const out: string[] = [];
    for (let i = 0; out.length < 14 && lists.some((l) => i < l.length); i += 1) {
      for (const l of lists) if (i < l.length && out.length < 14 && !out.includes(l[i])) out.push(l[i]);
    }
    return out;
  }, [orgs, icons]);
  const chosen = found ? found.candidates.filter((c) => selected.has(c.channel_id)) : [];

  return (
    <ChannelIconContext.Provider value={icons}>
    <div className="az">
      <section className="az-hero2" aria-label="Organization analysis">
        <div className="az-hero2__text">
          <span className="az-hero2__kicker"><Icon name="search" size={14} /> Organization analysis</span>
          <h1>Analyze an organization</h1>
          <p>Search any YouTube media organization, confirm its channels and run a quick audience-bridge analysis on a fresh sample.</p>
          <div className="az-hero2__stats">
            <span><b>{orgs.length}</b> organizations</span>
            <span><b>{orgs.filter((o) => o.complete).length}</b> fully analysed</span>
            <span><b>{cfg ? cfg.limits.max_videos_per_channel : "—"}</b> videos / channel</span>
          </div>
        </div>
        {cloud.length > 0 && (
          <div className="az-hero2__cloud" aria-hidden="true">
            {cloud.map((id, i) => (
              <span key={id} className="az-hero2__bubble" style={{ ["--i" as string]: i }}><ChannelAvatar id={id} name={id} size={i % 3 === 0 ? 58 : i % 3 === 1 ? 46 : 38} /></span>
            ))}
          </div>
        )}
      </section>

      {config.status === "error" && <ErrorState error={config.error} onRetry={config.reload} what="analysis settings" />}
      {cfg && !cfg.enabled && (
        <Notice>Organization analysis is switched off on this server (<code>API_ENABLE_ANALYSIS=false</code>). Stored results stay available.</Notice>
      )}

      <ol className="az-track" aria-label="Steps">
        {["Find channels", "Confirm channels", "Analyze"].map((s, i) => (
          <li key={s} className={`${step === i + 1 ? "is-now" : ""}${step > i + 1 ? " is-done" : ""}`}>
            <span className="az-track__dot">{step > i + 1 ? "✓" : i + 1}</span>
            <span className="az-track__label">{s}</span>
          </li>
        ))}
      </ol>

      {job ? (
        <JobProgress job={job} onOpen={open} onReset={reset} />
      ) : (
        <>
          <section className="az-panel az-panel--search" aria-label="Find the organization's channels">
            <form className="az-search" onSubmit={search} role="search" aria-label="Search organization">
              <div className="field az-search__name">
                <label htmlFor="az-org">Organization or main channel</label>
                <div className="az-search__box">
                  <Icon name="search" size={20} />
                  <input id="az-org" className="az-input" value={query} onChange={(e) => setQuery(e.target.value)}
                    placeholder="e.g. Sirasa, Hiru, Swarnavahini" maxLength={60} autoComplete="off" disabled={!enabled} />
                  <select id="az-region" aria-label="Region" value={region} onChange={(e) => setRegion(e.target.value)} disabled={!enabled}>
                    {REGIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                  <button type="submit" className="az-search__go" disabled={searching || query.trim().length < 2 || !enabled}>
                    {searching ? "Searching YouTube…" : "Search"}
                  </button>
                </div>
              </div>
            </form>
            <div className="az-suggest" aria-label="Suggestions">
              <span>Try</span>
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="az-chip" disabled={!enabled || searching} onClick={() => setQuery(s)}>{s}</button>
              ))}
            </div>
            {searching && <Loading label="Searching YouTube for channels…" variant="cards" rows={6} />}
            {searchError && <p className="az-error" role="alert">{searchError}</p>}
          </section>

          {found && (
            <section className="az-panel" aria-label="Confirm channels">
              <header className="az-panel__head az-panel__head--row">
                <div><h2>Confirm channels</h2><p>{found.candidates.length} found for “{found.organization}”. High-confidence channels are pre-selected.</p>
                  {found.source === "saved" && (
                    <p className="az-saved">Saved results from {date(found.discovered_at)} · no quota used ·{" "}
                      <button type="button" className="link-button" onClick={refresh} disabled={searching || !enabled}>Search YouTube again</button></p>
                  )}
                </div>
                <div className="az-pick" role="group" aria-label="Quick selection">
                  <button type="button" className="az-chip" onClick={() => pick("high")}>High confidence</button>
                  <button type="button" className="az-chip" onClick={() => pick("medium")}>High + medium</button>
                  <button type="button" className="az-chip" onClick={() => pick("none")}>Clear</button>
                </div>
              </header>
              {found.candidates.length === 0 ? (
                <p className="muted">No channels were found. Try the organization's exact channel name.</p>
              ) : (
                <ul className="az-cards">
                  {found.candidates.map((c) => {
                    const on = selected.has(c.channel_id);
                    return (
                      <li key={c.channel_id} className={`az-ccard az-ccard--${c.confidence}${on ? " is-on" : ""}`}>
                        <label>
                          <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(c.channel_id)} aria-label={`Include ${c.title}`} />
                          <span className="az-ccard__check" aria-hidden="true">✓</span>
                          <span className="az-ccard__icon"><ChannelAvatar id={c.channel_id} name={c.title} size={56} /></span>
                          <strong className="az-ccard__title">{c.title}</strong>
                          <span className="az-ccard__handle">{[c.handle, c.country].filter(Boolean).join(" · ") || c.channel_id}</span>
                          <span className="az-ccard__meta">
                            <span><b>{c.subscriber_count === null ? "hidden" : compact(c.subscriber_count)}</b> subscribers</span>
                            <Badge tone={CONFIDENCE_TONE[c.confidence]}>{c.confidence}</Badge>
                          </span>
                          <span className="az-ccard__evidence" title={c.evidence.join(" · ")}>{c.evidence.join(" · ")}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className="az-footer">
                <div className="az-footer__sel">
                  <span className="az-stack" aria-hidden="true">
                    {chosen.slice(0, 6).map((c) => <ChannelAvatar key={c.channel_id} id={c.channel_id} name={c.title} size={30} />)}
                    {chosen.length > 6 && <span className="az-stack__more">+{chosen.length - 6}</span>}
                  </span>
                  <div>
                    <strong>{count} selected</strong>
                    <span className="muted">
                      {tooFew ? ` · select at least ${min} channels (a bridge needs two)` : tooMany ? ` · at most ${max} channels`
                        : ` · about ${minutes} min · ${cfg?.limits.max_videos_per_channel ?? 15} newest videos and ${cfg?.limits.max_threads_per_video ?? 50} comment threads per video`}
                    </span>
                  </div>
                </div>
                <button type="button" className="az-go" onClick={analyze}
                  disabled={tooFew || tooMany || starting || running || !enabled}>
                  {starting ? "Starting…" : `Analyze ${count} channels`}
                </button>
              </div>
              {startError && <p className="az-error" role="alert">{startError}</p>}
              <p className="muted az-hint">
                Quick analysis collects a fresh sample, creates a snapshot for this organization only and computes topic
                similarity, metapath2vec, Personalized PageRank, the Audience Bridge Score, the Louvain baseline and explanations.
                Results are potential audience bridges, not audience migration.
              </p>
            </section>
          )}
        </>
      )}

      {orgs.length > 0 && (
        <section className="az-panel" aria-label="Recent analyses">
          <header className="az-panel__head az-panel__head--row">
            <div><h2>Recent analyses</h2><p>Latest analysis and strongest bridge per organization.</p></div>
            {compare.length > 0 && <span className="az-cmp__hint">{compare.length === 1 ? "Pick one more organization to compare" : "Comparing 2 organizations"}</span>}
          </header>
          {compare.length === 2 && (() => {
            const pickOrg = (n: string) => orgs.find((o) => o.name === n);
            const snap = (n: string) => pickOrg(n)?.quick?.result?.snapshot_id ?? pickOrg(n)?.complete?.snapshot_id ?? null;
            const [x, y] = compare;
            const sx = snap(x), sy = snap(y);
            return sx && sy ? <OrgCompare a={sx} b={sy} names={[titleCase(x), titleCase(y)]} onClose={() => setCompare([])} /> : null;
          })()}
          <div className="az-orgs">
            {orgs.map((o) => {
              const rows = o.quick?.result?.rows;
              const snapshot = o.quick?.result?.snapshot_id ?? o.complete?.snapshot_id ?? null;
              const active = o.latest.status === "running" || o.latest.status === "queued";
              const failed = o.latest.status === "failed" || o.latest.status === "interrupted";
              const chans = o.quick?.channels ?? [];
              const lead = chans.find((c) => icons.has(c.channel_id)) ?? chans[0];
              const color = orgColor(o.name);
              return (
                <article key={o.name} className="az-org" style={{ ["--org" as string]: color }}>
                  <div className="az-org__band" aria-hidden="true" />
                  <header>
                    <span className="az-org__logo">
                      {lead ? <ChannelAvatar id={lead.channel_id} name={lead.title} size={52} />
                        : <span className="az-org__mark" style={{ background: color }}>{o.name.slice(0, 1).toUpperCase()}</span>}
                    </span>
                    <div>
                      <strong>{titleCase(o.name)}</strong>
                      <span>{date(o.latest.created_at).slice(0, 10)}</span>
                    </div>
                    {active ? <Badge tone="warn">running</Badge> : failed ? <Badge tone="bad">{o.latest.status}</Badge>
                      : o.complete ? <Badge tone="ok">fully analysed</Badge> : <Badge tone="neutral">quick only</Badge>}
                  </header>
                  {chans.length > 0 && (
                    <span className="az-stack" aria-label={`${chans.length} channels`}>
                      {chans.slice(0, 8).map((c) => <ChannelAvatar key={c.channel_id} id={c.channel_id} name={c.title} size={30} />)}
                      {chans.length > 8 && <span className="az-stack__more">+{chans.length - 8}</span>}
                    </span>
                  )}
                  <dl className="az-org__stats">
                    <div><dt>channels</dt><dd>{int(rows?.channels ?? (chans.length || null))}</dd></div>
                    <div><dt>videos</dt><dd>{int(rows?.videos ?? null)}</dd></div>
                    <div><dt>comments</dt><dd>{int(rows?.comments ?? null)}</dd></div>
                  </dl>
                  {snapshot && !active && !failed && <OrgTopBridge snapshotId={snapshot} />}
                  {failed && o.latest.error && <p className="az-org__err">{o.latest.error}</p>}
                  <footer>
                    {snapshot && !active && !failed ? (
                      <label className={`az-cmp__pick${compare.includes(o.name) ? " is-on" : ""}`}>
                        <input type="checkbox" checked={compare.includes(o.name)} aria-label={`Compare ${titleCase(o.name)}`}
                          disabled={!compare.includes(o.name) && compare.length >= 2}
                          onChange={() => setCompare((c) => (c.includes(o.name) ? c.filter((n) => n !== o.name) : [...c, o.name].slice(-2)))} />
                        Compare
                      </label>
                    ) : snapshot ? <code className="az-org__sid">{snapshot}</code> : <span />}
                    {active ? (
                      <button type="button" className="link-button" onClick={() => follow(o.latest.job_id)}>Show progress</button>
                    ) : snapshot && !failed ? (
                      <button type="button" className="link-button" onClick={() => open(snapshot)}>Open results</button>
                    ) : null}
                  </footer>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </div>
    </ChannelIconContext.Provider>
  );
}
