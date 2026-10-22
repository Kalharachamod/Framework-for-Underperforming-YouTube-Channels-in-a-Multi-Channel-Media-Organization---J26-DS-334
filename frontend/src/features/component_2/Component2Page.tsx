import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Fold } from "../../components/common/Fold";
import { Icon } from "../../components/common/Icon";
import { Badge, Card, Notice, Select, StatCard, StatGrid, TableWrap, type Tone } from "../../components/common/ui";
import {
  COMPONENT_TITLE, EVIDENCE_DATE, dreamStarGap, calibration, comparisons, evidenceUrl, examples,
  futurePipeline, partitionFingerprint, partitions, pilot, researchQuestions, reviewQueue, stages, taxonomy,
  type ResearchStage, type StageStatus,
  dataFlow,
  novelty,
  requestThemes,
  researchGap,
} from "./researchData";
import "./component2.css";

const statusTone: Record<StageStatus, Tone> = { Completed: "ok", Diagnostic: "warn", Redesigned: "warn", "In progress": "warn", Planned: "neutral" };
const signalLabel = Object.fromEntries(taxonomy.map(([code, title]) => [code, title])) as Record<string, string>;
const number = (value: number) => value.toLocaleString("en-US");
const percent = (numerator: number, denominator: number) => `${(100 * numerator / denominator).toFixed(2)}%`;

function EvidenceLink({ children = "View evidence register" }: { children?: string }) {
  return <a className="c2-evidence" href={evidenceUrl} target="_blank" rel="noreferrer">{children} <span aria-hidden="true">↗</span></a>;
}

function CalibrationResults() {
  const [selected, setSelected] = useState<"tp" | "fp" | "fn" | "tn">("fp");
  const explanations = {
    tp: "5 true positives: the screener flagged comments that the researcher judged actionable YES.",
    fp: "13 false positives: the screener flagged comments judged NO. Praise, current-topic discussion and generic lexical cues generated false alarms.",
    fn: "1 false negative: the screener missed a researcher-approved YES storyline preference expressed through Sinhala narrative context.",
    tn: "19 true negatives: the screener did not flag comments judged NO by the researcher.",
  };
  const cells = [{ key: "tp", label: "True positive", count: calibration.tp }, { key: "fp", label: "False positive", count: calibration.fp }, { key: "fn", label: "False negative", count: calibration.fn }, { key: "tn", label: "True negative", count: calibration.tn }] as const;
  return <div className="c2-stack">
    <StatGrid label="Calibration diagnostics">
      <StatCard label="Precision" value={percent(calibration.tp, calibration.tp + calibration.fp)} hint="5 of 18 evaluable flags were actionable" tone="warn" />
      <StatCard label="Recall" value={percent(calibration.tp, calibration.tp + calibration.fn)} hint="5 of 6 actionable requests found" />
      <StatCard label="F1" value={percent(2 * calibration.tp, 2 * calibration.tp + calibration.fp + calibration.fn)} hint="Balance of precision and recall" />
      <StatCard label="Eight-category agreement" value={percent(calibration.categoryMatches, calibration.total)} hint="15/40 · rules versus researcher labels" />
    </StatGrid>
    <div className="c2-two">
      <figure className="c2-matrix">
        <figcaption>Binary confusion matrix <small>Click a cell to explain it · 38 evaluable comments</small></figcaption>
        <div className="c2-matrix__grid">
          <span aria-hidden="true" /><span>Human YES</span><span>Human NO</span>
          {[0, 1].map((row) => <div className="c2-matrix__row" key={row}>
            <span>Rule {row === 0 ? "candidate" : "non-candidate"}</span>
            {cells.slice(row * 2, row * 2 + 2).map((cell) => <button type="button" key={cell.key} className={`c2-matrix__cell c2-matrix__cell--${cell.key}`} aria-pressed={selected === cell.key} aria-label={`${cell.label}: ${cell.count}`} onClick={() => setSelected(cell.key)}><b>{cell.count}</b><small>{cell.label}</small></button>)}
          </div>)}
        </div>
        <p className="c2-explanation" aria-live="polite">{explanations[selected]}</p>
      </figure>
      <div className="c2-stack c2-reading">
        <h3>High recall still permits many false alarms</h3>
        <p>The rules found most actionable cases in this set, but only 5 of the 18 flagged comments were genuine requests. This motivated trained classifiers, which raised F1 from 0.35 to 0.54 on the larger batch.</p>
        <p><strong>Human decisions:</strong> 6 YES, 32 NO, 2 UNCLEAR. The two UNCLEAR cases are excluded from binary metrics, while all 40 remain in the category comparison.</p>
        <Notice>Design: 20 rule candidates + 20 controls, chosen to expose the strengths and errors of the keyword rules.</Notice>
      </div>
    </div>
  </div>;
}

function PartitionDiagram() {
  const [unit, setUnit] = useState("comments");
  const key = unit === "comments" ? "comments" : "videos";
  const total = unit === "comments" ? pilot.comments : pilot.coveredVideos;
  return <div className="c2-stack">
    <div className="c2-row">
      <h3>Frozen video-grouped partition</h3>
      <Select id="c2-partition-unit" label="Partition measure" value={unit} onChange={setUnit} options={[{ value: "comments", label: "Comments" }, { value: "videos", label: "Videos" }]} />
    </div>
    <figure className="c2-partition">
      <figcaption>{number(total)} {unit} · each video has exactly one role</figcaption>
      <div className="c2-partition__bar" aria-hidden="true">{partitions.map((partition) => <span className={`c2-fill--${partition.className}`} key={partition.role} style={{ flex: partition[key] }}>{number(partition[key])}</span>)}</div>
      <ul className="c2-partition__legend">{partitions.map((partition) => <li key={partition.role}><span className={`c2-dot c2-fill--${partition.className}`} aria-hidden="true" /><strong>{partition.role}</strong><b>{number(partition[key])} {unit}</b><p>{partition.description}</p></li>)}</ul>
    </figure>
    <TableWrap label="Partition counts"><table className="table"><thead><tr><th scope="col">Role</th><th scope="col">Comments</th><th scope="col">Videos</th></tr></thead><tbody>{partitions.map((partition) => <tr key={partition.role}><th scope="row">{partition.role}</th><td className="num">{number(partition.comments)}</td><td className="num">{partition.videos}</td></tr>)}</tbody></table></TableWrap>
    <div className="c2-two">
      <div className="c2-inset"><h3>94-comment development queue</h3><p><strong>{reviewQueue.rule}</strong> rule candidates + <strong>{reviewQueue.supplementary}</strong> supplementary candidates + <strong>{reviewQueue.controls}</strong> matched controls.</p><p>Candidate/control provenance is hidden from the annotator. The queue was labelled in annotation batch 1.</p></div>
      <div className="c2-inset"><h3>Reproducible safeguards</h3><p>Seed 20261018; channel/time strata; source checksums and a frozen partition fingerprint. Future training must use the guard to reject protected, unknown or conflicting identifiers.</p><p className="c2-fingerprint">Partition SHA-256 <code>{partitionFingerprint}</code></p></div>
    </div>
  </div>;
}

function LeakageDemo() {
  const [grouped, setGrouped] = useState(false);
  return <div className="c2-stack">
    <figure className="c2-old-split"><figcaption>Original full-video allocation · 2,000 comments</figcaption><div className="c2-partition__bar" aria-hidden="true"><span className="c2-old-evaluation" style={{ flex: 1825 }}>1,825</span><span className="c2-old-enriched" style={{ flex: 20 }} /><span className="c2-fill--development" style={{ flex: 155 }}>155</span></div><p>Evaluation videos: <b>1,825</b> · enriched development videos: <b>20</b> · future training: <b>155</b>. The boundary avoided crossing videos, but consumed 91.25% of the pilot for evaluation.</p></figure>
    <div className="c2-inset c2-stack">
      <div className="c2-row"><div><h3>Why group by video?</h3><p className="muted">Illustrative teaching example · these are not research records</p></div><button type="button" className="button" aria-pressed={grouped} onClick={() => setGrouped(!grouped)}>{grouped ? "Show comment-level split" : "Keep whole videos together"}</button></div>
      <div className="c2-two">{["A", "B"].map((video, videoIndex) => <div className="c2-video" key={video}><strong>Example video {video}</strong><div className="c2-video__comments">{[1, 2, 3].map((comment) => { const development = grouped ? videoIndex === 0 : comment !== 2; return <span key={comment} className={development ? "c2-demo-dev" : "c2-demo-test"}>Comment {video}{comment}<small>{development ? "Development" : "Evaluation"}</small></span>; })}</div></div>)}</div>
      <p className="c2-explanation" aria-live="polite">{grouped ? "Video groups are disjoint: all A comments stay in development; all B comments stay in evaluation. This keeps evaluation independent of the training context." : "Context crosses the boundary: comments about each video appear on both sides. A method may recognize shared video context rather than generalize to new videos."}</p>
    </div>
  </div>;
}

function TaxonomyPanel() {
  return <div className="c2-stack"><p><strong>Two decisions:</strong> what signal does the comment express, and is there an actionable channel content request? Record requested topic, action, format and target to support the decision.</p><div className="c2-taxonomy">{taxonomy.map(([code, title, description]) => <details key={code}><summary>{title}</summary><p>{description}</p><code>{code}</code></details>)}</div><p className="provenance">Definitions: decision_guide.md and annotation_schema_v1.md.</p></div>;
}

function StageContent({ stage }: { stage: ResearchStage }) {
  const fields = [["Intention", stage.intent], ["Why this method", stage.rationale], ["Data", stage.data], ["Implementation", stage.implementation], ["Evidence and results", stage.evidence], ["What we discovered", stage.problem], ["Next step", stage.next]];
  return <div className="c2-stack"><dl className="c2-stage-fields">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {stage.id === "taxonomy" && <TaxonomyPanel />}
    {stage.id === "calibration" && <CalibrationResults />}
    {stage.id === "leakage" && <LeakageDemo />}
    {stage.id === "split" && <PartitionDiagram />}
    <p className="c2-source"><strong>Evidence:</strong> {stage.source}. <EvidenceLink /></p>
  </div>;
}

function ResearchTimeline() {
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState(false);
  const visible = stages.filter((stage) => filter === "all" || stage.status === filter);
  return <section id="c2-progress" className="c2-stack c2-section" aria-labelledby="c2-progress-title">
    <div className="c2-section-heading"><div><span className="c2-kicker">B · Evidence-backed development timeline</span><h2 id="c2-progress-title">How the methodology evolved from pilot data to trained models</h2><p>Each stage connects a research decision to its evidence, limitation and next action.</p></div><span className="c2-stage-count">{stages.length} documented stages</span></div>
    <div className="c2-row c2-controls"><Select id="c2-stage-status" label="Filter research stages" value={filter} onChange={setFilter} options={[{ value: "all", label: "All stages" }, ...[...new Set(stages.map((stage) => stage.status))].map((value) => ({ value, label: value }))]} /><button type="button" className="button" onClick={() => setExpanded(!expanded)}>{expanded ? "Collapse all stages" : "Expand all stages"}</button><span className="muted" aria-live="polite">{visible.length} {visible.length === 1 ? "stage" : "stages"} shown</span></div>
    <div className="c2-timeline">{visible.map((stage) => <div className="c2-stage" key={stage.id}><span className="c2-stage__number" aria-hidden="true">{stages.indexOf(stage) + 1}</span><Fold title={stage.title} badge={<Badge tone={statusTone[stage.status]}>{stage.status}</Badge>} open={expanded}><StageContent stage={stage} /></Fold></div>)}</div>
  </section>;
}

function ExamplesPanel() {
  const [filter, setFilter] = useState("all");
  const visible = examples.filter((example) => filter === "all" || example.signal === filter);
  const count = (code: string) => examples.filter((example) => example.signal === code).length;
  return <section id="c2-examples" className="c2-stack c2-section" aria-labelledby="c2-examples-title"><div className="c2-section-heading"><div><span className="c2-kicker">C · Annotated examples</span><h2 id="c2-examples-title">Annotated examples for each of the eight audience signals</h2><p>Each card shows the comment, the researcher's decision, the primary audience signal and how the keyword rules handled it.</p></div></div>
    <Select id="c2-example-filter" label="Audience signal" value={filter} onChange={setFilter} options={[{ value: "all", label: `All eight signals (${examples.length})` }, ...taxonomy.map(([code, title]) => ({ value: code, label: `${title} (${count(code)})` }))]} />
    <div className="c2-examples">{visible.map((example) => <article className={`c2-example${example.illustrative ? " c2-example--illustrative" : ""}`} key={example.title}><div className="c2-row c2-example__header"><h3>{example.title}</h3><Badge tone={example.illustrative ? "neutral" : "ok"}>{signalLabel[example.signal]}</Badge></div><p className="c2-example__video"><span>Video</span>{example.videoTitle} · {example.channel}</p><div className="c2-example__quote"><span>Comment</span><blockquote>{example.text}</blockquote></div><dl><div className="c2-example__outcome"><dt>{example.illustrative ? "Interpretation" : "Researcher decision"}</dt><dd>{example.human}</dd></div><div><dt>Primary audience signal</dt><dd>{example.signal.replaceAll("_", " ")}</dd></div><div><dt>Rule baseline</dt><dd>{example.baseline}</dd></div><div><dt>Rule outcome</dt><dd>{example.ruleOutcome}</dd></div></dl><p className="c2-example__explanation"><strong>Why:</strong> {example.explanation}</p><p className="c2-source">{example.source}</p></article>)}</div><EvidenceLink /></section>;
}

function ComparisonPanel() {
  const [index, setIndex] = useState("0");
  const comparison = comparisons[Number(index)];
  return <section id="c2-methods" className="c2-stack c2-section" aria-labelledby="c2-methods-title"><div className="c2-section-heading"><div><span className="c2-kicker">D · Research design improvements</span><h2 id="c2-methods-title">Why the revised methodology is more defensible</h2><p>Compare each earlier decision with the corrected method and its research consequence.</p></div></div><Card><div className="c2-stack"><Select id="c2-comparison" label="Compare methodology" value={index} onChange={setIndex} options={comparisons.map((item, i) => ({ value: String(i), label: item.title }))} /><div className="c2-two" aria-live="polite"><div className="c2-inset"><span className="c2-kicker">Earlier approach</span><p>{comparison.before}</p></div><div className="c2-inset c2-inset--revised"><span className="c2-kicker">Revised approach / plan</span><p>{comparison.after}</p></div></div><p><strong>Why this matters:</strong> {comparison.why}</p></div></Card></section>;
}

const GAP_AXIS_MAX = 50;

function JsdScale({ selected }: { selected: string }) {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return <figure className="c2-jsd-scale" aria-label={`Jensen–Shannon divergence on a 0 to 1 scale. ${dreamStarGap.windows.map((w) => `${w.label}: ${w.jsd.toFixed(3)}`).join("; ")}.`}>
    <figcaption>Jensen–Shannon divergence <small>0 = identical distributions · 1 = completely different</small></figcaption>
    <div className="c2-jsd-scale__track" aria-hidden="true">
      {dreamStarGap.windows.map((period) => <span key={period.id} className={`c2-jsd-scale__marker${period.id === selected ? " is-selected" : ""}`} style={{ left: `${period.jsd * 100}%` }}><b>{period.jsd.toFixed(3)}</b><small>{period.label}</small></span>)}
      {dreamStarGap.windows.filter((period) => period.id === selected).map((period) => <span key="range" className="c2-jsd-scale__range" style={{ left: `${period.jsdRange[0] * 100}%`, width: `${(period.jsdRange[1] - period.jsdRange[0]) * 100}%` }} />)}
    </div>
    <div className="c2-jsd-scale__ticks" aria-hidden="true">{ticks.map((tick) => <span key={tick} style={{ left: `${tick * 100}%` }}>{tick}</span>)}</div>
  </figure>;
}

function DataFlowPanel() {
  const flow = dataFlow;
  const splitTotal = flow.split.reduce((sum, part) => sum + part.comments, 0);
  const pct = (value: number, total: number) => `${((value / total) * 100).toFixed(1)}%`;
  return <section id="c2-flow" className="c2-stack c2-section" aria-labelledby="c2-flow-title"><div className="c2-section-heading"><div><span className="c2-kicker">The data, step by step</span><h2 id="c2-flow-title">How {number(flow.collected.comments)} comments become the gap chart</h2><p>Each number below comes from the step before it.</p></div></div>
    <ol className="c2-flow">
      <li className="c2-flow__step"><span className="c2-flow__num" aria-hidden="true">1</span><div className="c2-flow__body"><h3>Collect public comments and videos</h3>
        <div className="c2-flow__bignums"><span><b>{number(flow.collected.comments)}</b> comments</span><span><b>{number(flow.collected.videos)}</b> videos</span><span><b>{flow.collected.channels}</b> Derana channels</span></div>
        <p>From the YouTube Data API, April 2025 to October 2026. Only public data is used, and commenter IDs are stored as salted hashes.</p></div></li>
      <li className="c2-flow__step"><span className="c2-flow__num" aria-hidden="true">2</span><div className="c2-flow__body"><h3>Split by video: train, test and set aside</h3>
        <div className="c2-flow__split" role="img" aria-label={`The ${number(splitTotal)} comments are split into ${flow.split.map((part) => `${part.label} ${number(part.comments)}`).join(", ")}`}>{flow.split.map((part) => <span key={part.key} className={`c2-flow__seg c2-flow__seg--${part.key}`} style={{ flexGrow: part.comments }} />)}</div>
        <ul className="c2-flow__legend">{flow.split.map((part) => <li key={part.key}><i className={`c2-flow__dot c2-flow__seg--${part.key}`} /><b>{number(part.comments)}</b> {part.label} <small>{pct(part.comments, splitTotal)} · {part.note}</small></li>)}</ul>
        <p>Whole videos go to one group, so no video is in both training and testing. 15% of videos were held out at random, and a code check blocks them from training.</p></div></li>
      <li className="c2-flow__step"><span className="c2-flow__num" aria-hidden="true">3</span><div className="c2-flow__body"><h3>Label a sample by hand</h3>
        <div className="c2-flow__bignums"><span><b>{flow.labelled.batch + flow.labelled.calibration}</b> comments labelled</span><span><b>{flow.labelled.binary}</b> with a clear YES or NO</span></div>
        <div className="c2-flow__split c2-flow__split--thin" role="img" aria-label={`${flow.labelled.yes} requests and ${flow.labelled.no} non-requests`}><span className="c2-flow__seg c2-flow__seg--yes" style={{ flexGrow: flow.labelled.yes }} /><span className="c2-flow__seg c2-flow__seg--no" style={{ flexGrow: flow.labelled.no }} /></div>
        <ul className="c2-flow__legend"><li><i className="c2-flow__dot c2-flow__seg--yes" /><b>{flow.labelled.yes}</b> requests (YES)</li><li><i className="c2-flow__dot c2-flow__seg--no" /><b>{flow.labelled.no}</b> not requests (NO)</li></ul>
        <p>Each comment got one of eight audience signals and a request label. These labels are the answer key the models learn from and are tested against.</p></div></li>
      <li className="c2-flow__step"><span className="c2-flow__num" aria-hidden="true">4</span><div className="c2-flow__body"><h3>Compare four ways to find requests</h3>
        <ol className="c2-flow__f1" aria-label="F1 score of each method on the 490 labelled comments">{flow.methods.map((method) => <li key={method.name} className={method.chosen ? "is-chosen" : undefined}><span>{method.name}</span><div className="c2-flow__f1bar" aria-hidden="true"><span style={{ width: `${method.f1 * 100}%` }} /></div><b>{method.f1.toFixed(2)}</b><small>precision {method.precision.toFixed(2)} · recall {method.recall.toFixed(2)}</small></li>)}</ol>
        <p>All four were scored on the same 490 comments. The trained methods were tested on videos they were not trained on (5 splits, repeated 5 times). The keyword rules have no training, so they were run once.</p>
        <div className="c2-flow__note"><strong>Score meanings</strong><dl><div><dt>Precision</dt><dd>Of the comments flagged as requests, how many really are.</dd></div><div><dt>Recall</dt><dd>Of all the real requests, how many were found.</dd></div><div><dt>F1</dt><dd>Both combined into one score from 0 to 1. It is high only when both are good.</dd></div></dl><p>The rules flag many wrong comments and miss over half the requests (F1 0.35). The e5 model finds about 8 in 10 requests, with some false flags (F1 0.54).</p></div></div></li>
      <li className="c2-flow__step"><span className="c2-flow__num" aria-hidden="true">5</span><div className="c2-flow__body"><h3>Train two models on the labels</h3>
        <div className="c2-two">{flow.models.map((model) => <div key={model.name} className="c2-flow__model"><strong>{model.name}</strong><p>{model.question}</p><dl><div><dt>Trained on</dt><dd>{model.labels}</dd></div><div><dt>Used for</dt><dd>{model.use}</dd></div><div><dt>Score</dt><dd>{model.score}</dd></div></dl></div>)}</div>
        <p>Both use e5 embeddings with logistic regression, the best method in step 4. Once chosen, each was retrained on all of its labels.</p></div></li>
      <li className="c2-flow__step"><span className="c2-flow__num" aria-hidden="true">6</span><div className="c2-flow__body"><h3>Apply to Dream Star</h3>
        <ol className="c2-flow__funnel" aria-label="Dream Star comments kept at each stage">
          <li><span className="c2-flow__funnelbar" style={{ width: "100%" }}><b>{number(flow.dreamStar.pool)}</b>&nbsp;training comments</span></li>
          <li><span className="c2-flow__funnelbar c2-flow__funnelbar--b" style={{ width: pct(flow.dreamStar.meaningful, flow.dreamStar.pool) }} /><span className="c2-flow__funnellabel"><b>{number(flow.dreamStar.meaningful)}</b> meaningful</span></li>
          <li><span className="c2-flow__funnelbar c2-flow__funnelbar--c" style={{ width: pct(flow.dreamStar.season2025, flow.dreamStar.pool) }} /><span className="c2-flow__funnellabel"><b>{number(flow.dreamStar.season2025)}</b> posted in Season 2025</span></li>
        </ol>
        <p>The meaningful-comment filter reads Dream Star's training comments and drops reactions, emoji and spam. The Season 2025 comments feed the topics and the gap chart below.</p></div></li>
    </ol>
    <Notice><strong>How to read the scores.</strong> The F1 values come from the 490 labelled comments, where requests are over-represented ({pct(flow.labelled.yes, flow.labelled.binary)} against 6% in a random sample). The other comments are unlabelled and the held-out comments are not labelled yet, so these scores are not the accuracy on all comments.</Notice>
  </section>;
}

function GapNoveltyPanel() {
  return <section id="c2-why" className="c2-stack c2-section" aria-labelledby="c2-why-title"><div className="c2-section-heading"><div><span className="c2-kicker">Research gap and novelty</span><h2 id="c2-why-title">What is missing, and what this component adds</h2></div></div>
    <div className="c2-two"><Card title="Research gap"><dl className="c2-terms">{researchGap.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}</dl></Card>
    <Card title="Novelty"><div className="c2-stack"><p><strong>{novelty.statement}</strong></p><dl className="c2-terms">{novelty.parts.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}</dl></div></Card></div>
  </section>;
}

function RequestsPanel() {
  const max = Math.max(...requestThemes.map((theme) => theme.count));
  const total = requestThemes.reduce((sum, theme) => sum + theme.count, 0);
  const supplyable = requestThemes.filter((theme) => theme.canSupply).reduce((sum, theme) => sum + theme.count, 0);
  return <section id="c2-requests" className="c2-stack c2-section" aria-labelledby="c2-requests-title"><div className="c2-section-heading"><div><span className="c2-kicker">Viewer requests</span><h2 id="c2-requests-title">What viewers asked for, and whether the channel can supply it</h2><p>{total} comments labelled as actionable requests, grouped by what they ask for. {supplyable} of them ask for something the channel can supply directly.</p></div></div>
    <figure className="c2-requests" aria-labelledby="c2-requests-chart-title">
      <div className="c2-row"><figcaption id="c2-requests-chart-title"><strong>Requests by theme</strong> <span className="muted">· number of labelled requests</span></figcaption><div className="c2-gap-legend" aria-hidden="true"><span><i className="c2-swatch c2-swatch--interest" />Channel can supply</span><span><i className="c2-swatch c2-swatch--feedback" />Programme feedback</span></div></div>
      <ol className="c2-request-rows">{requestThemes.map((theme) => <li key={theme.label} className="c2-request-row">
        <div className="c2-request-row__head"><div className="c2-gap-row__label"><strong>{theme.label}</strong><small>{theme.channels}</small></div>
          <div className="c2-gap-bar" aria-label={`${theme.label}: ${theme.count} requests`}><span className={`c2-gap-bar__fill ${theme.canSupply ? "c2-gap-bar__fill--interest" : "c2-gap-bar__fill--feedback"}`} style={{ width: `${(theme.count / max) * 100}%` }} /><b>{theme.count}</b></div>
          <Badge tone={theme.canSupply ? "ok" : "neutral"}>{theme.canSupply ? "Channel can supply" : "Programme feedback"}</Badge></div>
        <details className="c2-request-row__examples"><summary>{theme.action} · example comments</summary><ul>{theme.examples.map((example) => <li key={example.text}><q>{example.text}</q> <small>{example.channel}</small></li>)}</ul></details>
      </li>)}</ol>
    </figure>
    <p className="provenance">From the 85 comments the researcher labelled as actionable (79 in annotation batch 1, 6 in calibration). Most were found through search, so the counts show what kinds of requests exist, not how common each is among all viewers. The theme grouping is provisional until the researcher verifies it.</p>
  </section>;
}

function GapPanel() {
  const [selected, setSelected] = useState(dreamStarGap.windows[0].id);
  const [showTable, setShowTable] = useState(false);
  const period = dreamStarGap.windows.find((item) => item.id === selected)!;
  const topics = [...period.topics].sort((a, b) => b.jsdContribution - a.jsdContribution);
  const share = (topic: { jsdContribution: number }) => (topic.jsdContribution / period.jsdExact) * 100;
  const shownShare = topics.reduce((sum, topic) => sum + share(topic), 0);
  return <section id="c2-gap" className="c2-stack c2-section" aria-labelledby="c2-gap-title"><div className="c2-section-heading"><div><span className="c2-kicker">E · Demand–supply gap · {dreamStarGap.channel} · {period.label} ({period.period})</span><h2 id="c2-gap-title">Where audience attention and published content differ</h2><p>Topics are discovered from meaningful audience comments; each video is placed in its nearest topic. The JSD score measures the overall difference, and each topic's share of it shows where it comes from.</p></div></div>
    {dreamStarGap.windows.length > 1 && <div className="c2-segmented" role="group" aria-label="Analysis period">{dreamStarGap.windows.map((item) => <button type="button" key={item.id} aria-pressed={item.id === selected} onClick={() => setSelected(item.id)}>{item.label}<small>{item.period}</small></button>)}</div>}
    <StatGrid label={`${period.label} gap summary`}><StatCard label="JSD (interest vs supply)" value={period.jsd.toFixed(3)} hint={`stable ${period.jsdRange[0].toFixed(2)}–${period.jsdRange[1].toFixed(2)} across 10–25 topics`} /><StatCard label="Meaningful comments" value={number(period.comments)} hint="audience interest" /><StatCard label="Videos" value={number(period.videos)} hint="published supply" /></StatGrid>
    <JsdScale selected={selected} />
    <figure className="c2-gap-chart" aria-labelledby="c2-gap-chart-title">
      <div className="c2-row"><figcaption id="c2-gap-chart-title"><strong>Audience interest vs published supply by topic</strong> <span className="muted">· share of each side, %</span></figcaption><div className="c2-gap-legend" aria-hidden="true"><span><i className="c2-swatch c2-swatch--interest" />Audience interest</span><span><i className="c2-swatch c2-swatch--supply" />Published supply</span></div></div>
      <ol className="c2-gap-rows">{topics.map((topic) => <li key={topic.name} className="c2-gap-row" aria-label={`${topic.name}: audience interest ${topic.interest}%, published supply ${topic.supply}%, ${share(topic).toFixed(1)}% of the JSD`}>
        <div className="c2-gap-row__label"><strong>{topic.name}</strong><small>{topic.keywords}</small></div>
        <div className="c2-gap-row__bars" aria-hidden="true">
          <div className="c2-gap-bar"><span className="c2-gap-bar__fill c2-gap-bar__fill--interest" style={{ width: `${(topic.interest / GAP_AXIS_MAX) * 100}%` }} title={`Audience interest ${topic.interest}% · ${number(topic.comments)} comments`} /><b>{topic.interest.toFixed(1)}%</b></div>
          <div className="c2-gap-bar"><span className="c2-gap-bar__fill c2-gap-bar__fill--supply" style={{ width: `${(topic.supply / GAP_AXIS_MAX) * 100}%` }} title={`Published supply ${topic.supply}% · ${number(topic.videos)} videos`} /><b>{topic.supply.toFixed(1)}%</b></div>
        </div>
        <span className="c2-gap-value"><b>{share(topic).toFixed(1)}%</b><small>of the JSD</small></span>
      </li>)}</ol>
      <p className="c2-gap-axis">Bar scale 0–{GAP_AXIS_MAX}% · the right-hand figure is each topic's share of the overall JSD, so the larger it is, the more of the mismatch that topic explains.</p>
    </figure>
    <button type="button" className="button c2-table-toggle" aria-expanded={showTable} onClick={() => setShowTable(!showTable)}>{showTable ? "Hide data table" : "Show data table"}</button>
    {showTable && <TableWrap label={`${period.label} topic shares`}><table className="table"><thead><tr><th scope="col">Topic</th><th scope="col">Comments</th><th scope="col">Interest %</th><th scope="col">Videos</th><th scope="col">Supply %</th><th scope="col">Share of JSD</th></tr></thead><tbody>{topics.map((topic) => <tr key={topic.name}><th scope="row">{topic.name}</th><td className="num">{number(topic.comments)}</td><td className="num">{topic.interest.toFixed(1)}</td><td className="num">{topic.videos}</td><td className="num">{topic.supply.toFixed(1)}</td><td className="num">{share(topic).toFixed(1)}%</td></tr>)}</tbody></table></TableWrap>}
    <Fold title="How these numbers were produced" hint="Method"><div className="c2-stack">
      <p><strong>Why Dream Star.</strong> It holds 51,742 of the 84,002 collected comments (44,070 in the training pool), runs in clear seasons, and its titles name the song and contestant, so the supply text describes the content. It is the proof-of-concept case, not an underperforming channel.</p>
      <p><strong>Meaningful comments.</strong> Held-out comments are excluded. A multilingual-e5 + logistic regression filter (F1 0.88) keeps comments that say something about content; 12,239 of them were posted in Season 2025.</p>
      <p><strong>Why multilingual-e5.</strong> It reads Sinhala script, Singlish and English in one model, places comments and video text in one shared space, and found the most requests in the classifier tests (recall 0.79 against 0.37–0.43 for TF-IDF). It runs on a laptop CPU and is pinned to one model revision.</p>
      <p><strong>Script normalisation.</strong> Embeddings are centred within each script group and each domain (comments, videos). Without this, 890 of 967 videos fell into one topic because of writing style alone.</p>
      <p><strong>Why k-means.</strong> BERTopic's default density clustering (HDBSCAN) put 80% of comments into one topic. k-means assigns every comment to one of 15 topics, gives each topic a centre that videos can be matched to, and allows the stability check over 10–25 topics. Topic labels are each topic's top words.</p>
      <p><strong>Supply and JSD.</strong> Each of the 896 Season 2025 videos (title and cleaned description) is placed in its nearest topic. Interest % = topic comments ÷ 12,239 and supply % = topic videos ÷ 896, so each side sums to 100%. Example: 1,261 ÷ 12,239 = 10.3% and 20 ÷ 896 = 2.2%. JSD = ½ Σ P·log₂(P/M) + ½ Σ Q·log₂(Q/M) with M = (P + Q) ÷ 2. Each topic adds a term to the sum; the 15 terms add up to 0.155, and the chart shows each topic's share of it (for example, "Songs and lyrics" adds 0.024, which is 15.6%).</p>
    </div></Fold>
    <Fold title="What the checks showed" hint="Limitations"><div className="c2-stack">
      <p><strong>A topic label is not demand.</strong> Viewers are asked to vote every week, so "vote" comments are campaigning, reactions or complaints about the system. A contestant's name appears in criticism as well as support.</p>
      <p><strong>Video placement is the weak step.</strong> Performance videos were placed in the "Judges debate" (170 videos) and "Votes, SMS and wild card" (123 videos) topics, and only 42.5% of videos share a keyword with their topic. The calculation is exact, but the supply shares depend on this placement.</p>
      <p><strong>Attention depends on season and month.</strong> Voting talk fell from 14.5% of interest in July 2025 to 3.9% in November, and Season 12 names carried over into Season 13.</p>
      <p><strong>Supply can only be measured when titles describe the content.</strong> This works for Dream Star but not for FM Derana, whose titles name episodes rather than themes.</p>
      <p><strong>Next stage.</strong> Each comment's target, stance and intent will be read before it is counted as demand, and supply will be counted per contestant from the titles.</p>
    </div></Fold>
    <Fold title="Terms and methods compared" hint="Definitions"><div className="c2-stack">
      <dl className="c2-terms">
        <div><dt>Audience interest</dt><dd>What the audience talks about: all meaningful comments, grouped into topics. This is what the chart shows.</dd></div>
        <div><dt>Explicit requests</dt><dd>Comments that ask the channel to do something, such as "upload the Season 10 group songs". About 6% of random comments.</dd></div>
        <div><dt>Audience demand</dt><dd>The general term covering both.</dd></div>
      </dl>
      <TableWrap label="Methods compared"><table className="table"><thead><tr><th scope="col">Stage</th><th scope="col">Compared</th><th scope="col">Result</th><th scope="col">Kept</th></tr></thead><tbody>
        <tr><th scope="row">Request search (2B)</th><td>Word, character and combined TF-IDF</td><td>18% of retrieved comments were requests, against 6% at random</td><td>Combined TF-IDF, as a search step only</td></tr>
        <tr><th scope="row">Supply topics (3B)</th><td>LDA vs BERTopic</td><td>Coherence c_v 0.407 vs 0.687</td><td>BERTopic</td></tr>
        <tr><th scope="row">Request classifier (3D)</th><td>Keyword rules, TF-IDF + logistic regression, TF-IDF + SVM, e5 + logistic regression</td><td>F1 0.35, 0.50, 0.47, 0.54</td><td>e5 + logistic regression (highest recall, 0.79)</td></tr>
        <tr><th scope="row">Meaningful filter (3E)</th><td>4-word rule, TF-IDF models, e5 + logistic regression</td><td>F1 0.85, 0.88, 0.88</td><td>e5, so the pipeline uses one representation</td></tr>
        <tr><th scope="row">Topic clustering (4A)</th><td>HDBSCAN vs k-means</td><td>HDBSCAN put 80% of comments in one topic</td><td>k-means</td></tr>
        <tr><th scope="row">Embeddings (4A)</th><td>Raw vs script- and domain-centred</td><td>Raw: 890 of 967 videos in one topic</td><td>Centred</td></tr>
        <tr><th scope="row">Number of topics (4A)</th><td>10, 15, 20, 25</td><td>JSD 0.12–0.24</td><td>15 for display</td></tr>
      </tbody></table></TableWrap>
      <p><strong>Topic names.</strong> BERTopic gives each topic its top words, such as "pahanmi · anupama · janani". The readable names in the chart were written from those words, so they are an interpretation.</p>
      <p><strong>Requests.</strong> Request probabilities from the e5 classifier are corrected to the natural request rate (prior shift) and summed per topic. The request-vs-supply JSD is 0.140, close to the interest JSD, because the classifier separates requests only weakly, so the chart shows interest only.</p>
      <p><strong>Not yet compared.</strong> Other embedding models, other gap measures (KL, Hellinger, Wasserstein) and LLM extraction.</p>
    </div></Fold>
    <p className="provenance">Interest = share of meaningful comments in the period; supply = share of videos published in the period. Each topic's share of the JSD is its contribution to the overall mismatch. The ten topics shown account for {shownShare.toFixed(1)}% of the JSD; the other five add {(100 - shownShare).toFixed(1)}%. The output is evidence for content planning, not a fixed threshold. Season 2025 runs from April 2025 to January 2026; Season 13 is not shown yet.</p>
  </section>;
}

function ValidationPanel() {
  const steps = [
    ["Gap observed", "In one period, a topic receives more audience attention than published coverage."],
    ["Covered later?", "In the following period, check whether the channel published videos on that topic."],
    ["Did it perform better?", "Compare those videos with the channel's normal, age-adjusted views, and compare the gap ranking with a ranking by popularity alone."],
  ];
  const shifts = [
    { topic: "Votes, SMS and wild card", points: [["July 2025", "14.5%"], ["November 2025", "3.9%"]], outcome: "Attention fell during the season" },
    { topic: "Nipuni and her songs", points: [["July 2025", "6.0%"], ["December 2025", "13.1%"]], outcome: "Attention rose towards the finals" },
  ];
  return <section id="c2-validation" className="c2-stack c2-section" aria-labelledby="c2-validation-title"><div className="c2-section-heading"><div><span className="c2-kicker">F · Validation</span><h2 id="c2-validation-title">Usefulness over time: do highlighted gaps matter later?</h2><p>The method does not set a fixed threshold for a gap. It is validated by checking what happened in the following period.</p></div></div>
    <ol className="c2-validation-steps">{steps.map(([title, text], index) => <li key={title}><span className="c2-validation-steps__number">{index + 1}</span><strong>{title}</strong><p>{text}</p></li>)}</ol>
    <p><strong>Why the periods must be short:</strong> within Season 2025, audience attention moved from one topic to another, so a gap is tied to the time it was observed.</p>
    <div className="c2-two">{shifts.map((item) => <Card key={item.topic} title={item.topic}><dl className="c2-validation-case">{item.points.map(([month, share]) => <div key={month}><dt>{month}</dt><dd>{share} of audience interest</dd></div>)}<div><dt>Observation</dt><dd><Badge tone="neutral">{item.outcome}</Badge></dd></div></dl></Card>)}</div>
    <Notice><strong>Each season is analysed with its own topics.</strong> Season 13 began in mid-September 2026. In its first weeks, 195 of 567 meaningful comments still discussed Season 12 contestants, so a combined analysis would mix the two seasons. Season 13 will be analysed with its own topics once enough comments and videos exist.</Notice>
    <p className="provenance">Monthly shares come from the Experiment 4A topics for Dream Star (Season 2025 comments). The follow-up and performance checks (steps 2 and 3) belong to the final evaluation stage.</p>
  </section>;
}

function FuturePanel() {
  const [selected, setSelected] = useState(1);
  return <section id="c2-pipeline" className="c2-stack c2-section" aria-labelledby="c2-pipeline-title"><div className="c2-section-heading"><div><span className="c2-kicker">G · Analytical pipeline</span><h2 id="c2-pipeline-title">From multilingual comments to content-gap evidence</h2><p>Each stage of the analytical pipeline and its current status.</p></div></div><Card><div className="c2-stack"><ol className="c2-pipeline">{futurePipeline.map((step, index) => <li key={step.name}><button type="button" aria-pressed={selected === index} onClick={() => setSelected(index)}><span className="c2-pipeline__number">{index + 1}</span><b>{step.name}</b><Badge tone={step.status === "Implemented" ? "ok" : step.status === "Partial" ? "warn" : "neutral"}>{step.status}</Badge></button></li>)}</ol><div className="c2-explanation" aria-live="polite"><strong>{futurePipeline[selected].name}</strong><p>{futurePipeline[selected].detail}</p></div><Fold title="How JSD is interpreted" hint="Method"><div className="c2-stack"><p>For aligned topic distributions P (demand) and Q (supply), let M = (P + Q) / 2.</p><p className="c2-formula">JSD(P, Q) = ½ KL(P ‖ M) + ½ KL(Q ‖ M)</p><p>JSD is symmetric: it summarizes overall mismatch without identifying an undersupplied topic. Directional interpretation compares P(topic) − Q(topic) and pairs each topic with its explicit request count before suggesting an opportunity.</p><p className="provenance">With base-2 logarithms, JSD ranges from 0 to 1. SciPy's function returns its square-root distance. <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html" target="_blank" rel="noreferrer">SciPy definition ↗</a></p></div></Fold></div></Card></section>;
}

export function Component2Page() {
  const [params] = useSearchParams();
  const demo = params.get("view") === "demo";
  const sections = demo
    ? [["why", "Gap and novelty"], ["flow", "Data flow"], ["examples", "Annotated examples"], ["requests", "Viewer requests"], ["gap", "Gap analysis"], ["validation", "Validation"]]
    : [["why", "Gap and novelty"], ["flow", "Data flow"], ["overview", "Study overview"], ["progress", "Development stages"], ["examples", "Annotated examples"], ["requests", "Viewer requests"], ["methods", "Design comparisons"], ["gap", "Gap analysis"], ["validation", "Validation"], ["pipeline", "Analysis pipeline"], ["questions", "Research Q&A"]];
  const viewSwitch = demo
    ? <Link className="button c2-view-switch" to="/component-2">Show full research view</Link>
    : <Link className="button c2-view-switch" to="/component-2?view=demo"><Icon name="play" size={16} /> Demo view</Link>;
  return <div className={`c2-page${demo ? " c2-page--demo" : ""}`}>
    <header className="c2-hero"><div className="c2-hero__body"><p className="c2-kicker">J26-DS-334 · {demo ? "Prototype demo" : `Research progress · Evidence as of ${EVIDENCE_DATE}`}</p><h1>{COMPONENT_TITLE}</h1><p>Identify genuine multilingual audience content demands, model audience demand and channel content supply in a shared semantic topic space, and quantify gaps using Jensen–Shannon Divergence.</p><div className="c2-hero__actions"><Link className="button c2-methodology-cta" to="/component-2/methodology"><Icon name="flow" size={18} /> Open Methodology Explorer <span aria-hidden="true">→</span></Link>{viewSwitch}</div>{!demo && <div className="c2-hero__tags"><Badge tone="ok">Corpus frozen</Badge><Badge tone="ok">Classifiers trained</Badge><Badge tone="ok">Supply topics modelled</Badge><Badge tone="warn">Gap analysis in progress</Badge></div>}</div><div className="c2-hero__aside"><Icon name="topic" size={30} /><strong>Demand topics and JSD</strong><span>Current milestone</span><p>Channel-specific demand topics compared with supply, validated season to season.</p></div></header>
    <nav className="c2-section-nav" aria-label="Component 2 sections">{sections.map(([id, label]) => <a key={id} href={`#c2-${id}`}>{label}</a>)}</nav>
    <GapNoveltyPanel />
    <DataFlowPanel />
    {demo && <><ExamplesPanel /><RequestsPanel /><GapPanel /><ValidationPanel /></>}
    {!demo && <>
    <section id="c2-overview" className="c2-stack c2-section" aria-labelledby="c2-overview-title"><div className="c2-section-heading"><div><span className="c2-kicker">A · Research purpose and current scope</span><h2 id="c2-overview-title">Research question and implementation boundary</h2><p>Does a channel publish what its audience talks about and asks for? The gap and novelty are below; then what has been built.</p></div></div></section>
    <section className="c2-stack c2-section" aria-label="Current implementation boundary"><Card title="Current implementation boundary"><div className="c2-two"><div className="c2-stack"><Badge tone="ok">Implemented / verified software</Badge><p>Collection, validation, multilingual preprocessing, the Streamlit annotation portal, rule screening, leakage audits, frozen partitions, the expanded 84k-comment corpus, 544 labelled comments, trained demand classifiers and supply topic modelling.</p></div><div className="c2-stack"><Badge tone="warn">In progress</Badge><p>Channel-specific demand topics, aligned demand and supply distributions, Jensen–Shannon Divergence with per-topic gaps, season-to-season validation and the final blind held-out evaluation.</p></div></div></Card><p className="provenance">Channels: Dream Star, Derana 60 Plus, Derana Little Star, FM Derana, Ada Derana Sports, Lokaya Saha Lokayo, TV Derana and Ada Derana. Conservative normalization preserves original language and emoji; exact source text is retained separately from NFC text. <EvidenceLink /></p></section>
    <ResearchTimeline />
    <ExamplesPanel />
    <RequestsPanel />
    <ComparisonPanel />
    <GapPanel />
    <ValidationPanel />
    <FuturePanel />
    <section id="c2-questions" className="c2-stack c2-section" aria-labelledby="c2-questions-title"><div className="c2-section-heading"><div><span className="c2-kicker">H · Key research questions</span><h2 id="c2-questions-title">Methodology questions and evidence-based answers</h2><p>Concise explanations of the research decisions and results.</p></div></div>{researchQuestions.map(([question, answer]) => <Fold key={question} title={question}><p className="c2-reading">{answer}</p>{question === "What is JSD?" && <p className="c2-source"><a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html" target="_blank" rel="noreferrer">SciPy mathematical definition ↗</a></p>}</Fold>)}</section>
    </>}
    <footer className="c2-footer"><p><strong>Evidence and scope.</strong> Verified on {EVIDENCE_DATE}. This page uses curated aggregates and minimized excerpts; no private datasets or commenter identifiers are included.</p><EvidenceLink /></footer>
  </div>;
}
