import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChannelAvatar } from "../../../components/common/ChannelAvatar";
import { ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, Notice, PageHeader, type Tone } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { ApiError, describeError } from "../../../services/apiClient";
import { compact, date, int } from "../../../utils/format";
import { analysisApi, type AnalysisJob, type Candidate, type DiscoveryResponse, type JobStep } from "../analysisApi";
import { CompleteAnalysisButton } from "../QuickAnalysis";
import { useResearch } from "../ResearchContext";

const POLL_MS = 2000;
const REGIONS = [
  { value: "LK", label: "Sri Lanka" },
  { value: "IN", label: "India" },
  { value: "", label: "Any region" },
];
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
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

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
      const res = await analysisApi.discover(name, region);
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

  const open = (snapshotId: string, page = "/") => {
    setSnapshotId(snapshotId);
    navigate(page);
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
  const pastJobs = (history.status === "success" ? history.data.items : []).filter((j) => j.job_id !== job?.job_id).slice(0, 6);

  return (
    <>
      <PageHeader title="Analyze an organization"
        description="Search any YouTube media organization, confirm its channels and run a quick audience-bridge analysis on a fresh sample." />

      {config.status === "error" && <ErrorState error={config.error} onRetry={config.reload} what="analysis settings" />}
      {cfg && !cfg.enabled && (
        <Notice>Organization analysis is switched off on this server (<code>API_ENABLE_ANALYSIS=false</code>). Stored results stay available.</Notice>
      )}

      {job ? (
        <JobProgress job={job} onOpen={open} onReset={reset} />
      ) : (
        <>
          <Card title="1 · Find the organization's channels">
            <form className="az-search" onSubmit={search} role="search" aria-label="Search organization">
              <div className="field az-search__name">
                <label htmlFor="az-org">Organization or main channel</label>
                <input id="az-org" className="az-input" value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. Sirasa, Hiru, Swarnavahini" maxLength={60} autoComplete="off" disabled={!cfg?.enabled} />
              </div>
              <div className="field az-search__region">
                <label htmlFor="az-region">Region</label>
                <select id="az-region" value={region} onChange={(e) => setRegion(e.target.value)} disabled={!cfg?.enabled}>
                  {REGIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              <button type="submit" className="button button--primary az-search__go" disabled={searching || query.trim().length < 2 || !cfg?.enabled}>
                {searching ? "Searching YouTube…" : "Search"}
              </button>
            </form>
            <p className="muted az-hint">
              Finds the main channel and the sub-channels it links to. A search uses about 100–150 of the 10,000 daily
              YouTube API quota units. YouTube does not publish ownership, so you confirm which channels belong.
            </p>
            {searching && <Loading label="Searching YouTube for channels…" variant="table" rows={4} />}
            {searchError && <p className="az-error" role="alert">{searchError}</p>}
          </Card>

          {found && (
            <Card title={`2 · Confirm channels (${found.candidates.length} found for “${found.organization}”)`}
              actions={
                <div className="az-pick" role="group" aria-label="Quick selection">
                  <button type="button" className="link-button" onClick={() => pick("high")}>High confidence</button>
                  <button type="button" className="link-button" onClick={() => pick("medium")}>High + medium</button>
                  <button type="button" className="link-button" onClick={() => pick("none")}>Clear</button>
                </div>
              }>
              {found.candidates.length === 0 ? (
                <p className="muted">No channels were found. Try the organization's exact channel name.</p>
              ) : (
                <ul className="az-list">
                  {found.candidates.map((c) => {
                    const on = selected.has(c.channel_id);
                    return (
                      <li key={c.channel_id} className={`az-cand${on ? " is-on" : ""}`}>
                        <label className="az-cand__main">
                          <input type="checkbox" checked={on} onChange={() => toggle(c.channel_id)} aria-label={`Include ${c.title}`} />
                          <ChannelAvatar id={c.channel_id} name={c.title} size={36} />
                          <span className="az-cand__text">
                            <strong>{c.title}</strong>
                            <span className="muted">{[c.handle, c.country].filter(Boolean).join(" · ") || c.channel_id}</span>
                          </span>
                        </label>
                        <span className="az-cand__subs">{c.subscriber_count === null ? "hidden" : compact(c.subscriber_count)}<small>subscribers</small></span>
                        <Badge tone={CONFIDENCE_TONE[c.confidence]}>{c.confidence}</Badge>
                        <span className="az-cand__evidence">{c.evidence.join(" · ")}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className="az-footer">
                <div>
                  <strong>{count} selected</strong>
                  <span className="muted">
                    {tooFew ? ` · select at least ${min} channels (a bridge needs two)` : tooMany ? ` · at most ${max} channels`
                      : ` · about ${minutes} min · ${cfg?.limits.max_videos_per_channel ?? 15} newest videos and ${cfg?.limits.max_threads_per_video ?? 50} comment threads per video`}
                  </span>
                </div>
                <button type="button" className="button button--primary" onClick={analyze}
                  disabled={tooFew || tooMany || starting || running || !cfg?.enabled}>
                  {starting ? "Starting…" : `Analyze ${count} channels`}
                </button>
              </div>
              {startError && <p className="az-error" role="alert">{startError}</p>}
              <p className="muted az-hint">
                Quick analysis: collects a fresh sample into the shared database, creates a snapshot for this organization only
                and computes topic similarity, metapath2vec, Personalized PageRank, the Audience Bridge Score, the Louvain
                baseline and explanations. HGT, node2vec and the full evaluation are skipped for speed. Results are potential
                audience bridges, not audience migration.
              </p>
            </Card>
          )}
        </>
      )}

      {pastJobs.length > 0 && (
        <Card title="Recent analyses">
          <ul className="az-history">
            {pastJobs.map((j) => (
              <li key={j.job_id}>
                <span className="az-history__org"><strong>{j.organization}{j.kind === "complete" ? " · completion" : ""}</strong><span className="muted">{j.kind === "complete" ? "HGT, node2vec, evaluation" : `${j.channels.length} channels`} · {date(j.created_at)}</span></span>
                <Badge tone={JOB_TONE[j.status]}>{j.status}</Badge>
                {j.status === "completed" && (j.result?.snapshot_id ?? j.snapshot_id) ? (
                  <button type="button" className="link-button" onClick={() => open((j.result?.snapshot_id ?? j.snapshot_id)!)}>Open results</button>
                ) : j.status === "running" || j.status === "queued" ? (
                  <button type="button" className="link-button" onClick={() => follow(j.job_id)}>Show progress</button>
                ) : <span className="muted az-history__err">{j.error ?? ""}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
