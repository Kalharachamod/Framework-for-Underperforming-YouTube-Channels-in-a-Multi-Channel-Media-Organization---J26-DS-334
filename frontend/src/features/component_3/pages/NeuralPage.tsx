import { Link, useSearchParams } from "react-router-dom";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowLane, type FlowNode } from "../../../components/charts/FlowCanvas";
import { LineChart } from "../../../components/charts/LineChart";
import { HgtRadial } from "../../../components/charts/HgtRadial";
import { SkipGram } from "../../../components/charts/SkipGram";
import { Icon } from "../../../components/common/Icon";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { date, int, label, num, pct } from "../../../utils/format";
import { component3Api } from "../api";
import { Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";
import type { EpochRecord, HgtModel, Metapath2VecModel, Scalar } from "../types";

const scalar = (v: Scalar | undefined) => (v === null || v === undefined ? "—" : typeof v === "boolean" ? (v ? "yes" : "no")
  : typeof v === "number" ? (Number.isInteger(v) ? int(v) : Math.abs(v) < 1e-3 ? v.toExponential(2) : String(Number(v.toPrecision(6)))) : v);
const asNum = (v: Scalar | undefined) => (typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : null);
const compactN = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);

/** Epoch with the smallest (or largest) value of a metric, read from the stored history. */
function best(history: EpochRecord[], key: keyof EpochRecord, mode: "min" | "max") {
  const rows = history.filter((h) => typeof h[key] === "number");
  if (!rows.length) return null;
  return rows.reduce((m, h) => ((mode === "min" ? (h[key] as number) < (m[key] as number) : (h[key] as number) > (m[key] as number)) ? h : m));
}

type Tone = "ok" | "stored" | "missing" | "neutral";
const toneOf = (m: { status: string; validation_passed?: boolean | null }): Tone => (m.status === "missing" ? "missing" : m.validation_passed ? "ok" : "stored");
const STATUS: Record<Tone, string> = { ok: "validated", stored: "stored", missing: "not run", neutral: "input" };

const TYPE_COLORS: Record<string, string> = { channel: "#2563eb", video: "#f43f5e", commenter: "#8b5cf6", topic: "#f59e0b" };
const WALK_COLORS = ["#6366f1", "#8b5cf6", "#ec4899", "#0ea5e9", "#f59e0b", "#10b981"];

/** Donut of stored walks per metapath, with a legend of the metapath chains. */
function WalkDonut({ metapaths, total }: { metapaths: import("../types").MetapathWalks[]; total: number | null }) {
  const sum = metapaths.reduce((a, m) => a + (m.walks ?? 0), 0) || 1;
  const R = 70, C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <div className="donut">
      <svg viewBox="0 0 200 200" role="img" aria-label={`Walks per metapath: ${metapaths.map((m) => `${m.metapath} ${m.walks}`).join(", ")}`}>
        <circle cx={100} cy={100} r={R} fill="none" stroke="#f1f5f9" strokeWidth={26} />
        {metapaths.map((m, i) => {
          const frac = (m.walks ?? 0) / sum, len = Math.max(0, C * frac - 2);
          const el = <circle key={m.metapath} cx={100} cy={100} r={R} fill="none" stroke={WALK_COLORS[i % WALK_COLORS.length]} strokeWidth={26}
            strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-acc} transform="rotate(-90 100 100)" />;
          acc += C * frac;
          return el;
        })}
        <text x={100} y={98} textAnchor="middle" className="donut__num">{compactN(total ?? sum)}</text>
        <text x={100} y={116} textAnchor="middle" className="donut__cap">walks</text>
      </svg>
      <ul className="donut__legend">
        {metapaths.map((m, i) => (
          <li key={m.metapath}>
            <i style={{ background: WALK_COLORS[i % WALK_COLORS.length] }} />
            <span className="mp-list__chain">
              {m.node_types.map((t, k) => <span key={k} className={`mp-node mp-node--${t}`} title={t}>{t.slice(0, 1).toUpperCase()}{t === "channel" ? "h" : ""}</span>)}
            </span>
            <b>{pct((m.walks ?? 0) / sum, 0)}</b>
            <small>{int(m.walks)} walks{m.truncated ? ` · ${int(m.truncated)} truncated` : ""}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Panel with a title row; the visual inside carries the content. */
function Block({ title, hint, label: aria, action, children }: { title: string; hint?: string; label?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="xblock" aria-label={aria ?? title}>
      <header className="xblock__head"><div><h3>{title}</h3>{hint && <p>{hint}</p>}</div>{action}</header>
      {children}
    </section>
  );
}

function NCard({ icon, color, title, value, text, tone, foot }: { icon: string; color: string; title: string; value: string; text: string; tone: Tone; foot?: string }) {
  return (
    <span className="schema-card">
      <span className="schema-card__head">
        <span className="gicon" style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, boxShadow: `0 3px 8px ${color}55` }}><Icon name={icon} size={16} /></span>
        <strong>{title}</strong><b>{value}</b>
      </span>
      <span className="schema-card__text">{text}</span>
      <span className="schema-card__foot"><span className={`gstatus gstatus--${tone}`}>{STATUS[tone]}</span>{foot && <span>{foot}</span>}</span>
    </span>
  );
}

/** How the embeddings are learned and where they are used, as a left-to-right card graph. */
const W = 1120, H = 316;
const LANES: FlowLane[] = [
  { id: "in", title: "Input", x: 8, y: 8, w: 232, h: H - 16 },
  { id: "models", title: "Neural models", x: 294, y: 8, w: 252, h: H - 16 },
  { id: "out", title: "Output", x: 600, y: 8, w: 232, h: H - 16 },
  { id: "use", title: "Used by", x: 886, y: 8, w: 226, h: H - 16 },
];

function ModelMap({ hgt, m2v, selected, onSelect }: { hgt: HgtModel; m2v: Metapath2VecModel; selected: string; onSelect: (id: string) => void }) {
  const types = Object.keys(hgt.node_features ?? {});
  const features = Object.values(hgt.node_features ?? {}).reduce((a, f) => a + f.length, 0);
  const dims = m2v.dimensions ?? hgt.dimensions ?? null;
  const nodes: FlowNode[] = [
    { id: "graph", x: 18, y: 112, w: 212, h: 112, tone: "neutral", selected: selected === "graph", label: "Heterogeneous graph: model input",
      content: <NCard icon="graph" color="#1e3a8a" title="Graph" value={types.length ? `${types.length} types` : ""} text={features ? `${features} input features · heterogeneous` : "channels, videos, commenters, topics"} tone="neutral" foot="STEP 13" /> },
    { id: "m2v", x: 306, y: 44, w: 228, h: 112, tone: toneOf(m2v), selected: selected === "m2v", label: `metapath2vec: ${m2v.status === "available" ? "stored" : "Not run"}`,
      content: <NCard icon="route" color="#6366f1" title="metapath2vec" value={m2v.dimensions ? `${m2v.dimensions}-dim` : ""} text={`${m2v.metapaths?.length ?? 0} metapaths · ${compactN(m2v.total_walks)} walks`} tone={toneOf(m2v)} foot="primary" /> },
    { id: "hgt", x: 306, y: 182, w: 228, h: 112, tone: toneOf(hgt), selected: selected === "hgt", label: `HGT: ${hgt.status === "available" ? "stored" : "Not run"}`,
      content: <NCard icon="neural" color="#a855f7" title="HGT" value={hgt.dimensions ? `${hgt.dimensions}-dim` : ""} text={`${int(asNum(hgt.config?.layers))} layers × ${int(asNum(hgt.config?.heads))} heads · ${int(hgt.history?.length ?? null)} epochs`} tone={toneOf(hgt)} foot="alternative" /> },
    { id: "emb", x: 610, y: 112, w: 212, h: 112, tone: m2v.status === "available" || hgt.status === "available" ? "ok" : "missing", selected: selected === "emb", label: "Channel embeddings: model output",
      content: <NCard icon="channels" color="#0ea5e9" title="Embeddings" value={dims ? `${dims}-dim` : ""} text={`one vector per channel · coverage ${pct(m2v.coverage_ratio ?? hgt.coverage_ratio ?? null, 0)}`} tone={m2v.status === "available" || hgt.status === "available" ? "ok" : "missing"} /> },
    { id: "abs", x: 896, y: 112, w: 206, h: 112, tone: "neutral", selected: selected === "abs", label: "Audience Bridge Score: embedding component",
      content: <NCard icon="bridges" color="#16a34a" title="Bridge score" value="" text="cosine similarity → embedding component" tone="neutral" foot="STEP 19" /> },
  ];
  const edges: FlowEdge[] = [
    { from: "graph", to: "m2v", dir: "right", color: "#6366f1", width: 2, label: "walks" },
    { from: "graph", to: "hgt", dir: "right", color: "#a855f7", width: 2, label: "attention" },
    { from: "m2v", to: "emb", dir: "right", color: "#6366f1", width: 2.5, label: "primary" },
    { from: "hgt", to: "emb", dir: "right", color: "#a855f7", width: 1.5, dashed: true, label: "alt." },
    { from: "emb", to: "abs", dir: "right", color: "#0ea5e9", width: 2.5, label: "cosine" },
  ];
  return (
    <>
      <FlowLegend items={[
        { kind: "dot", tone: "ok", label: "Stored · validated" }, { kind: "dot", tone: "stored", label: "Stored" }, { kind: "dot", tone: "missing", label: "Not run" },
        { kind: "line", label: "Feeds into" }, { kind: "dash", label: "Alternative source" },
      ]} />
      <FlowCanvas width={W} height={H} lanes={LANES} nodes={nodes} edges={edges} onSelect={onSelect} label="Neural model map" minScale={0.55} />
    </>
  );
}

function Chips({ rows }: { rows: [string, string][] }) {
  return <ul className="model__chips">{rows.map(([k, v]) => <li key={k}><span>{k}</span><b>{v}</b></li>)}</ul>;
}

/** Drawer content for the selected card. */
function Details({ id, hgt, m2v }: { id: string; hgt: HgtModel; m2v: Metapath2VecModel }) {
  const cfg = hgt.config ?? {};
  if (id === "m2v") return m2v.status === "missing" ? <EmptyState title="Not run" /> : (
    <>
      <Chips rows={[["Run", m2v.experiment_id ?? "—"], ["Created", date(m2v.created_at ?? null)], ["Dimensions", scalar(m2v.config?.dimensions)],
        ["Window", scalar(m2v.config?.window)], ["Negatives", scalar(m2v.config?.negative)], ["Walks per node", scalar(m2v.config?.walks_per_node)],
        ["Walk length", `${scalar(m2v.config?.walk_length)} (mean ${num(m2v.mean_walk_length ?? null, 1)})`], ["Epochs", scalar(m2v.config?.epochs)],
        ["Learning rate", scalar(m2v.config?.learning_rate)], ["Coverage", pct(m2v.coverage_ratio ?? null)]]} />
    </>
  );
  if (id === "hgt") return hgt.status === "missing" ? <EmptyState title="Not run" /> : (
    <Chips rows={[["Run", hgt.experiment_id ?? "—"], ["Role", hgt.role ?? "—"], ["Objective", hgt.objective ?? "—"], ["Hidden size", scalar(cfg.hidden)],
      ["Layers × heads", `${scalar(cfg.layers)} × ${scalar(cfg.heads)}`], ["Dropout", scalar(cfg.dropout)], ["Learning rate", scalar(cfg.learning_rate)],
      ["Weight decay", scalar(cfg.weight_decay)], ["Negatives per positive", scalar(hgt.negative_sampling?.per_positive)], ["Split cutoff", date(hgt.split?.cutoff ?? null)],
      ["Training time", hgt.duration_seconds ? `${num(hgt.duration_seconds, 1)} s` : "—"]]} />
  );
  if (id === "graph") return (
    <ul className="feat-list">
      {Object.entries(hgt.node_features ?? {}).map(([t, fs]) => (
        <li key={t}><span className={`mp-node mp-node--${t}`}>{t.slice(0, 1).toUpperCase()}</span><strong>{t}</strong><span>{fs.map((f) => label(f)).join(" · ")}</span></li>
      ))}
    </ul>
  );
  if (id === "emb") return (
    <>
      <p className="small">Each channel gets one {m2v.dimensions ?? hgt.dimensions ?? "—"}-dimensional vector. metapath2vec vectors are the primary source of the score; HGT vectors are the stored alternative.</p>
      <Chips rows={[["metapath2vec coverage", pct(m2v.coverage_ratio ?? null)], ["HGT coverage", pct(hgt.coverage_ratio ?? null)]]} />
    </>
  );
  if (id === "abs") return (
    <>
      <p className="small">The cosine similarity of two channels' embeddings, weighted, is the score's embedding component (alongside diffusion and topic similarity).</p>
      <p className="small"><Link to="/explainability">See a score decomposition →</Link></p>
    </>
  );
  return null;
}

const TITLES: Record<string, string> = { graph: "Research graph (input)", m2v: "metapath2vec", hgt: "HGT", emb: "Channel embeddings", abs: "Audience Bridge Score" };

export function NeuralPage() {
  const { snapshotId } = useResearch();
  const [params, setParams] = useSearchParams();
  const selected = params.get("model") ?? "";
  const nm = useApi((s) => component3Api.neuralModels({ snapshotId }, s), [snapshotId]);

  return (
    <>
      {nm.status === "loading" && <Loading variant="graph" label="Loading model records…" />}
      {nm.status === "error" && <ErrorState error={nm.error} onRetry={nm.reload} what="Neural model records" />}
      {nm.status === "success" && (() => {
        const { hgt, metapath2vec: m2v } = nm.data;
        const cfg = hgt.config ?? {};
        const hist = hgt.history ?? [];
        const last = hist[hist.length - 1];
        const minValid = best(hist, "valid_loss", "min");
        const maxAuc = best(hist, "valid_roc_auc", "max");
        return (
          <div className="gx">
            <section className="xhero gx__hero" aria-label="Model summary">
              <span className="gx__mark" aria-hidden="true"><Icon name="neural" size={32} /></span>
              <div className="xhero__id">
                <h1>Neural graph models</h1>
                <p>HGT and metapath2vec learn channel embeddings from the research graph; they feed the score's embedding component.</p>
                <ul className="gx__legend nm-status">
                  <li><span className={`gstatus gstatus--${toneOf(m2v)}`}>metapath2vec · {STATUS[toneOf(m2v)]}</span></li>
                  <li><span className={`gstatus gstatus--${toneOf(hgt)}`}>HGT · {STATUS[toneOf(hgt)]}</span></li>
                  {hgt.duration_seconds ? <li>HGT trained in {num(hgt.duration_seconds, 1)} s</li> : null}
                </ul>
              </div>
              <div className="xhero__facts">
                <div><strong>{hgt.status === "available" ? `${int(asNum(cfg.layers))} × ${int(asNum(cfg.heads))}` : "—"}</strong><span>HGT layers × heads</span></div>
                <div><strong>{num(last?.valid_roc_auc ?? null, 3)}</strong><span>final valid ROC-AUC</span></div>
                <div><strong>{compactN(m2v.total_walks ?? null)}</strong><span>metapath2vec walks</span></div>
              </div>
            </section>

            <Block title="Model map" hint="How the embeddings are learned and where they are used. Click a card for its settings.">
              <ModelMap hgt={hgt} m2v={m2v} selected={selected} onSelect={(id) => setParams(id === selected ? {} : { model: id })} />
            </Block>

            <Block title="HGT neural network" hint="The trained graph neural network behind the embedding component, with our recorded input features and layer sizes."
              action={hgt.status === "available" ? <Badge tone={hgt.validation_passed ? "ok" : "warn"}>{hgt.validation_passed ? "validated run" : "not validated"}</Badge> : undefined}>
              {hgt.status === "missing" ? <EmptyState title="No HGT run is stored for this snapshot." /> : (
                <HgtRadial features={hgt.node_features ?? {}} hidden={asNum(cfg.hidden)} layers={asNum(cfg.layers) ?? 1}
                  heads={asNum(cfg.heads) ?? 1} dropout={asNum(cfg.dropout)} dims={hgt.dimensions ?? null} />
              )}
            </Block>

            <Block title="metapath2vec neural network" hint="The skip-gram network behind the primary embedding source: metapath walks train a one-layer network whose weights are the embeddings."
              action={m2v.status === "available" ? <Badge tone={m2v.validation_passed ? "ok" : "warn"}>{m2v.validation_passed ? "validated run" : "not validated"}</Badge> : undefined}>
              {m2v.status === "missing" ? <EmptyState title="The skip-gram network appears once metapath2vec has been run." /> : (
                <SkipGram metapaths={m2v.metapaths ?? []} window={asNum(m2v.config?.window)} negative={asNum(m2v.config?.negative)}
                  dims={m2v.dimensions ?? asNum(m2v.config?.dimensions)} walkLength={asNum(m2v.config?.walk_length)} />
              )}
            </Block>

            {hgt.status === "available" && hist.length > 0 && (
              <div className="xgrid xgrid--2">
                <Block title="Training and validation loss" hint="Binary cross-entropy per epoch, as recorded (lower is better).">
                  <ul className="nm-chips">
                    <li style={{ ["--c" as string]: "#f43f5e" }}><span>Best validation</span><b>{num(minValid?.valid_loss ?? null, 3)}</b><small>epoch {minValid?.epoch ?? "—"}</small></li>
                    <li style={{ ["--c" as string]: "#6366f1" }}><span>Final training</span><b>{num(last?.train_loss ?? null, 3)}</b><small>epoch {last?.epoch ?? "—"}</small></li>
                    <li style={{ ["--c" as string]: "#94a3b8" }}><span>Final validation</span><b>{num(last?.valid_loss ?? null, 3)}</b><small>epoch {last?.epoch ?? "—"}</small></li>
                  </ul>
                  <LineChart height={230} yLabel="Loss" labels={hist.map((h) => String(h.epoch))} summary="HGT training and validation loss per epoch"
                    marks={minValid ? [{ index: hist.indexOf(minValid), seriesKey: "valid", label: `best ${num(minValid.valid_loss, 3)}` }] : []}
                    series={[
                      { key: "train", label: "Training loss", color: "#6366f1", values: hist.map((h) => h.train_loss) },
                      { key: "valid", label: "Validation loss", color: "#f43f5e", values: hist.map((h) => h.valid_loss) },
                    ]} />
                  <p className="xnote">Lowest validation loss: {num(minValid?.valid_loss ?? null, 3)} at epoch {minValid?.epoch ?? "—"}; final: {num(last?.valid_loss ?? null, 3)}.</p>
                </Block>
                <Block title="Validation ranking quality" hint="Link-prediction ROC-AUC and average precision on held-out edges, per epoch.">
                  <ul className="nm-chips">
                    <li style={{ ["--c" as string]: "#0ea5e9" }}><span>Best ROC-AUC</span><b>{num(maxAuc?.valid_roc_auc ?? null, 3)}</b><small>epoch {maxAuc?.epoch ?? "—"}</small></li>
                    <li style={{ ["--c" as string]: "#0ea5e9" }}><span>Final ROC-AUC</span><b>{num(last?.valid_roc_auc ?? null, 3)}</b><small>epoch {last?.epoch ?? "—"}</small></li>
                    <li style={{ ["--c" as string]: "#f59e0b" }}><span>Final avg precision</span><b>{num(last?.valid_average_precision ?? null, 3)}</b><small>epoch {last?.epoch ?? "—"}</small></li>
                  </ul>
                  <LineChart height={230} yLabel="Metric" labels={hist.map((h) => String(h.epoch))} summary="HGT validation ROC-AUC and average precision per epoch"
                    marks={maxAuc ? [{ index: hist.indexOf(maxAuc), seriesKey: "auc", label: `best ${num(maxAuc.valid_roc_auc, 3)}` }] : []}
                    series={[
                      { key: "auc", label: "ROC-AUC", color: "#0ea5e9", values: hist.map((h) => h.valid_roc_auc) },
                      { key: "ap", label: "Average precision", color: "#f59e0b", values: hist.map((h) => h.valid_average_precision) },
                    ]} />
                  <p className="xnote">
                    Best ROC-AUC {num(maxAuc?.valid_roc_auc ?? null, 3)} at epoch {maxAuc?.epoch ?? "—"}. Validation set: {int(hgt.split?.validation_edges ?? null)} edges
                    ({hgt.split?.kind ?? "—"} split; {int(hgt.split?.train_edges ?? null)} training edges), so these values are indicative.
                  </p>
                </Block>
              </div>
            )}

            <div className="xgrid xgrid--2">
              <Block title="Walk share by metapath" hint="How the stored metapath2vec walks split across the metapaths (C commenter, V video, Ch channel, T topic).">
                {m2v.status === "missing" ? <EmptyState title="No metapath2vec run is stored for this snapshot." /> : (
                  <WalkDonut metapaths={m2v.metapaths ?? []} total={m2v.total_walks ?? null} />
                )}
              </Block>
              <Block title="HGT input features" hint="The features each node type brings into the network, as recorded by the run.">
                {hgt.status === "missing" ? <EmptyState title="No HGT run is stored for this snapshot." /> : (
                  <div className="feat-groups">
                    {Object.entries(hgt.node_features ?? {}).map(([t, fs]) => (
                      <div key={t} className="feat-group" style={{ ["--c" as string]: TYPE_COLORS[t] ?? "#64748b" }}>
                        <header><span className="feat-group__dot" />{t}<small>{fs.length} {fs.length === 1 ? "feature" : "features"}</small></header>
                        <ul>{fs.map((f) => <li key={f}>{label(f.replace(/^observed_/, "").replace(/_api_/, "_"))}</li>)}</ul>
                      </div>
                    ))}
                  </div>
                )}
              </Block>
            </div>

            {selected && TITLES[selected] && (
              <section className="xblock step-panel" aria-label={TITLES[selected]}>
                <header className="xblock__head">
                  <div><h3>{TITLES[selected]}</h3></div>
                  <button type="button" className="link-button" onClick={() => setParams({})}>Close</button>
                </header>
                <Details id={selected} hgt={hgt} m2v={m2v} />
              </section>
            )}
            <p className="xnote">{nm.data.note}</p>
            <Provenance snapshotId={nm.data.snapshot_id} extra={[hgt.experiment_id, m2v.experiment_id].filter(Boolean).join(" · ")} />
          </div>
        );
      })()}
    </>
  );
}
