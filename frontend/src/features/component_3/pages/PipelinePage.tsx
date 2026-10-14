import { Link, useSearchParams } from "react-router-dom";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowLane, type FlowNode } from "../../../components/charts/FlowCanvas";
import { ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { useResearch } from "../ResearchContext";
import type { GraphSummaryResponse, ResearchRun, ResearchRunsResponse, ResearchStatusResponse, Scalar } from "../types";

type Tone = "ok" | "stored" | "missing" | "failed";
interface Step {
  id: string;
  title: string;
  step: string;
  icon: string;
  x: number;
  y: number;
  to: string;
  tone: Tone;
  runId: string | null;
  chips: string[];
}

const W = 1200, CW = 250, CH = 134;
const LANES: FlowLane[] = [
  { id: "data", title: "Data · steps 12–14", x: 16, y: 12, w: W - 32, h: 190 },
  { id: "signals", title: "Representations and signals · steps 15–18", x: 16, y: 222, w: W - 32, h: 190 },
  { id: "scoring", title: "Scoring · step 19", x: 16, y: 432, w: W - 32, h: 190 },
  { id: "baselines", title: "Baselines · step 20", x: 16, y: 642, w: W - 32, h: 190 },
  { id: "validation", title: "Validation · steps 21–22", x: 16, y: 852, w: W - 32, h: 190 },
];
const H = 1060;
const row = (lane: number) => LANES[lane].y + 40;

const sci = (v: Scalar | undefined) => (typeof v === "number" ? (Math.abs(v) < 1e-3 && v !== 0 ? v.toExponential(0) : String(Number(v.toPrecision(4)))) : String(v ?? "—"));

function buildSteps(status: ResearchStatusResponse, graph: GraphSummaryResponse | null, runs: ResearchRunsResponse | null): Step[] {
  const art = (name: string) => status.artifacts.find((a) => a.name === name);
  const run = (kind: string, prefix?: string): ResearchRun | undefined =>
    runs?.items.find((r) => r.kind === kind && (!prefix || r.run_id.startsWith(prefix)));
  const tone = (available: boolean, r?: ResearchRun): Tone =>
    !available ? "missing" : r?.validation_passed === false ? "failed" : r?.validation_passed ? "ok" : "stored";
  const avail = (name: string) => art(name)?.status === "available";
  const rep = (m: string) => graph?.representations.find((r) => r.method === m);
  const dif = graph?.diffusion;
  const m2v = rep("metapath2vec"), hgt = rep("HGT");
  const abs = run("bridge"), ev = run("evaluation"), xp = run("explanations"), top = run("topics");
  return [
    { id: "snapshot", title: "Research snapshot", step: "STEP 12", icon: "S", x: 60, y: row(0), to: "/experiments",
      tone: status.research_data === "available" ? "ok" : "missing", runId: runs?.snapshot_id ?? status.snapshot_id,
      chips: runs ? [`channels ${int(runs.row_counts.channels)}`, `videos ${int(runs.row_counts.videos)}`, `comments ${int(runs.row_counts.comments)}`, "immutable"] : [] },
    { id: "graph", title: "Heterogeneous graph", step: "STEP 13", icon: "G", x: 475, y: row(0), to: "/graph",
      tone: tone(avail("heterogeneous_graph"), run("graph")), runId: "graph",
      chips: graph ? [`nodes ${int(graph.total_nodes)}`, `edges ${int(graph.total_edges)}`, `${Object.keys(graph.node_counts).length} node types`, `2+ ch ${int(graph.commenters_on_multiple_channels)}`] : [] },
    { id: "features", title: "Graph features", step: "STEP 14", icon: "F", x: 890, y: row(0), to: "/channels",
      tone: tone(avail("graph_features"), run("features")), runId: art("graph_features")?.latest_id ?? null,
      chips: graph ? [`pairs ${int(graph.channel_pairs_with_shared_commenters)}`, "as of snapshot"] : [] },
    { id: "m2v", title: "metapath2vec", step: "STEP 15 · primary", icon: "M", x: 40, y: row(1), to: "/graph",
      tone: m2v?.status === "available" ? (m2v.validation_passed ? "ok" : "stored") : "missing", runId: m2v?.experiment_id ?? null,
      chips: m2v?.status === "available" ? [`dim ${int(m2v.dimensions)}`, `cover ${pct(m2v.coverage_ratio)}`, ...(typeof m2v.config?.metapaths === "string" ? [`${m2v.config.metapaths.split(", ").length} metapaths`] : [])] : [] },
    { id: "hgt", title: "HGT", step: "STEP 16 · alternative", icon: "H", x: 330, y: row(1), to: "/graph",
      tone: hgt?.status === "available" ? (hgt.validation_passed ? "ok" : "stored") : "missing", runId: hgt?.experiment_id ?? null,
      chips: hgt?.status === "available" ? [`dim ${int(hgt.dimensions)}`, `cover ${pct(hgt.coverage_ratio)}`, ...(hgt.config?.layers !== undefined ? [`layers ${sci(hgt.config.layers)}`] : [])] : [] },
    { id: "ppr", title: "Personalized PageRank", step: "STEP 17", icon: "P", x: 620, y: row(1), to: "/graph",
      tone: dif?.status === "available" ? (dif.validation_passed ? "ok" : "stored") : "missing", runId: dif?.experiment_id ?? null,
      chips: dif?.status === "available" ? [`α ${sci(dif.alpha)}`, `tol ${sci(dif.tolerance)}`, `${int(dif.converged_sources)}/${int(dif.sources)} conv.`, `iter ${int(dif.iterations_max)}`] : [] },
    { id: "topic", title: "Topic similarity", step: "STEP 18", icon: "T", x: 910, y: row(1), to: "/topics",
      tone: tone(avail("topic_similarity"), top), runId: top?.run_id ?? null,
      chips: top ? [`topics ${sci(top.config.n_topics)}`, `backend ${sci(top.config.backend)}`, "cosine"] : [] },
    { id: "abs", title: "Audience Bridge Score", step: "STEP 19 · confidence weighted", icon: "A", x: 475, y: row(2), to: "/bridges",
      tone: tone(avail("audience_bridge_scores"), abs), runId: abs?.run_id ?? null,
      chips: abs ? [`w_d ${sci(abs.config.w_diffusion)}`, `w_e ${sci(abs.config.w_embedding)}`, `w_t ${sci(abs.config.w_topic)}`, `emb ${sci(abs.config.embedding_source)}`] : [] },
    { id: "louvain", title: "Louvain baseline", step: "STEP 20", icon: "L", x: 190, y: row(3), to: "/evaluation",
      tone: tone(avail("baseline_louvain"), run("baselines", "louvain")), runId: art("baseline_louvain")?.latest_id ?? null, chips: [] },
    { id: "node2vec", title: "node2vec baseline", step: "STEP 20", icon: "N", x: 760, y: row(3), to: "/evaluation",
      tone: tone(avail("baseline_node2vec"), run("baselines", "node2vec")), runId: art("baseline_node2vec")?.latest_id ?? null, chips: [] },
    { id: "eval", title: "Evaluation", step: "STEP 21", icon: "E", x: 330, y: row(4), to: "/evaluation",
      tone: tone(avail("evaluations"), ev), runId: ev?.run_id ?? null,
      chips: ev ? [`runs ${int(art("evaluations")?.count ?? null)}`, ...(ev.config.ks !== undefined ? [`k ${sci(ev.config.ks)}`] : []), ...(ev.config.run_temporal !== undefined ? [`temporal ${sci(ev.config.run_temporal)}`] : [])] : [] },
    { id: "xpl", title: "Explainability", step: "STEP 22", icon: "X", x: 760, y: row(4), to: "/explainability",
      tone: tone(avail("explanations"), xp), runId: xp?.run_id ?? null, chips: [] },
  ];
}

const EDGES: FlowEdge[] = [
  { from: "snapshot", to: "graph", dir: "right" },
  { from: "graph", to: "features", dir: "right" },
  { from: "graph", to: "m2v" }, { from: "graph", to: "hgt" }, { from: "graph", to: "ppr" },
  { from: "snapshot", to: "topic", label: "text" },
  { from: "m2v", to: "abs", label: "primary" }, { from: "hgt", to: "abs", dashed: true, label: "alt." },
  { from: "ppr", to: "abs" }, { from: "topic", to: "abs" },
  { from: "features", to: "abs", dashed: true, label: "evidence" },
  { from: "graph", to: "louvain", dashed: true, muted: true }, { from: "graph", to: "node2vec", dashed: true, muted: true },
  { from: "abs", to: "eval" }, { from: "abs", to: "xpl" },
  { from: "louvain", to: "eval", dashed: true, label: "compare" }, { from: "node2vec", to: "eval", dashed: true, label: "compare" },
];

const TONE_TEXT: Record<Tone, string> = { ok: "Stored · validated", stored: "Stored", missing: "Not run", failed: "Validation failed" };
const scalar = (v: Scalar) => (v === null ? "—" : typeof v === "boolean" ? (v ? "yes" : "no") : typeof v === "number"
  ? (Number.isInteger(v) ? int(v) : Math.abs(v) < 1e-3 ? v.toExponential(2) : String(Number(v.toPrecision(6)))) : v);

export function PipelinePage() {
  const { snapshotId, status } = useResearch();
  const [params, setParams] = useSearchParams();
  const selected = params.get("step") ?? "";
  const graph = useApi((s) => component3Api.graphSummary({ snapshotId }, s), [snapshotId]);
  const runs = useApi((s) => component3Api.researchRuns({ snapshotId }, s), [snapshotId]);

  if (status.status === "loading" || status.status === "idle") return <Loading label="Loading pipeline…" />;
  if (status.status === "error") return <ErrorState error={status.error} onRetry={status.reload} />;
  const steps = buildSteps(status.data, graph.status === "success" ? graph.data : null, runs.status === "success" ? runs.data : null);
  const sel = steps.find((s) => s.id === selected) ?? null;
  const selRun = sel && runs.status === "success" ? runs.data.items.find((r) => r.run_id === sel.runId) ?? null : null;
  const counts = steps.reduce((m, s) => ({ ...m, [s.tone]: (m[s.tone] ?? 0) + 1 }), {} as Record<Tone, number>);

  const nodes: FlowNode[] = steps.map((s) => ({
    id: s.id, x: s.x, y: s.y, w: CW, h: CH, tone: s.tone, selected: s.id === selected,
    label: `${s.title}, ${s.step}: ${TONE_TEXT[s.tone]}`,
    content: (
      <span className="fc">
        <span className="fc__head"><span className={`fc__icon tone-${s.tone}`}>{s.icon}</span><span className="fc__title">{s.title}</span></span>
        <span className="fc__step">{s.step}</span>
        <span className={`fc__status tone-${s.tone}`}>{TONE_TEXT[s.tone]}{s.runId ? <code className="fc__run">{s.runId}</code> : null}</span>
        <span className="fc__chips">{s.chips.slice(0, 4).map((c) => <span key={c} className="fc__chip">{c}</span>)}</span>
      </span>
    ),
  }));

  return (
    <>
      <PageHeader title="Pipeline Graph" description="The Component 3 research pipeline as stored runs: what feeds what, which steps ran, and their recorded settings." />
      <section className="rs-strip" aria-label="Pipeline status">
        <div className="rs-strip__cell"><span>Steps</span><strong>{steps.length}</strong></div>
        <div className="rs-strip__cell"><span>Validated</span><strong>{counts.ok ?? 0}</strong></div>
        <div className="rs-strip__cell"><span>Stored</span><strong>{counts.stored ?? 0}</strong><small>no validation recorded</small></div>
        <div className="rs-strip__cell"><span>Not run</span><strong>{counts.missing ?? 0}</strong></div>
        <div className="rs-strip__cell"><span>Snapshot</span><strong className="rs-strip__text">{status.data.snapshot_id ?? "—"}</strong></div>
      </section>
      <FlowLegend items={[
        { kind: "dot", tone: "ok", label: "Stored · validated" }, { kind: "dot", tone: "stored", label: "Stored" },
        { kind: "dot", tone: "missing", label: "Not run" }, { kind: "dot", tone: "failed", label: "Validation failed" },
        { kind: "line", label: "Feeds into" }, { kind: "dash", label: "Alternative / evidence / compared against" },
      ]} />
      <div className={sel ? "pipe pipe--with-panel" : "pipe"}>
        <div className="pipe__graph">
          <FlowCanvas width={W} height={H} lanes={LANES} nodes={nodes} edges={EDGES} label="Component 3 research pipeline"
            onSelect={(id) => setParams(id === selected ? {} : { step: id })} />
        </div>
        {sel && (
          <Card title={sel.title} actions={<button type="button" className="link-button" onClick={() => setParams({})}>Close</button>}>
            <KeyValues rows={[
              ["Pipeline step", sel.step],
              ["Status", <Badge key="s" tone={sel.tone === "ok" ? "ok" : sel.tone === "failed" ? "bad" : sel.tone === "missing" ? "warn" : "neutral"}>{TONE_TEXT[sel.tone]}</Badge>],
              ["Run", sel.runId ? <code key="r">{sel.runId}</code> : "—"],
              ["Created", selRun ? date(selRun.created_at) : "—"],
            ]} />
            {selRun && Object.keys(selRun.config).length > 0 && (
              <>
                <h3 className="sub-title">Recorded configuration</h3>
                <KeyValues rows={Object.entries(selRun.config).slice(0, 10).map(([k, v]) => [label(k), scalar(v)] as [string, string])} />
              </>
            )}
            <p className="small"><Link to={sel.to}>Open the related page →</Link></p>
          </Card>
        )}
      </div>
      {(graph.status === "error" || runs.status === "error") && (
        <p className="muted small">Some card details could not be loaded; statuses come from the research status endpoint.</p>
      )}
    </>
  );
}
