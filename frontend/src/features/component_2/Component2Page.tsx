import { useState } from "react";
import { Link } from "react-router-dom";
import { Fold } from "../../components/common/Fold";
import { Icon } from "../../components/common/Icon";
import { Badge, Card, Notice, Select, StatCard, StatGrid, TableWrap, type Tone } from "../../components/common/ui";
import {
  COMPONENT_TITLE, EVIDENCE_DATE, annotationBatch, bestClassifier, calibration, comparisons, corpus, evidenceUrl, examples,
  futurePipeline, partitionFingerprint, partitions, pilot, researchQuestions, reviewQueue, stages, supplyTopics, taxonomy,
  type ResearchStage, type StageStatus,
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
    <p className="provenance">Dates identify verified Git checkpoints and experiment runs.</p>
    <div className="c2-timeline">{visible.map((stage) => <div className="c2-stage" key={stage.id}><span className="c2-stage__number" aria-hidden="true">{stages.indexOf(stage) + 1}</span><Fold title={stage.title} hint={stage.date} badge={<Badge tone={statusTone[stage.status]}>{stage.status}</Badge>} open={expanded}><StageContent stage={stage} /></Fold></div>)}</div>
  </section>;
}

function ExamplesPanel() {
  const [filter, setFilter] = useState("all");
  const visible = examples.filter((example) => filter === "all" || example.signal === filter);
  const count = (code: string) => examples.filter((example) => example.signal === code).length;
  return <section id="c2-examples" className="c2-stack c2-section" aria-labelledby="c2-examples-title"><div className="c2-section-heading"><div><span className="c2-kicker">C · Annotated examples</span><h2 id="c2-examples-title">Annotated examples for each of the eight audience signals</h2><p>Each card shows the comment, the researcher's decision, the primary audience signal and how the keyword rules handled it.</p></div></div>
    <Select id="c2-example-filter" label="Audience signal" value={filter} onChange={setFilter} options={[{ value: "all", label: `All eight signals (${examples.length})` }, ...taxonomy.map(([code, title]) => ({ value: code, label: `${title} (${count(code)})` }))]} />
    <div className="c2-examples">{visible.map((example) => <article className={`c2-example${example.illustrative ? " c2-example--illustrative" : ""}`} key={example.title}><div className="c2-row c2-example__header"><h3>{example.title}</h3><Badge tone={example.illustrative ? "neutral" : "ok"}>{signalLabel[example.signal]}</Badge></div><div className="c2-example__quote"><span>Comment excerpt</span><blockquote>{example.text}</blockquote></div><dl><div className="c2-example__outcome"><dt>{example.illustrative ? "Interpretation" : "Researcher decision"}</dt><dd>{example.human}</dd></div><div><dt>Primary audience signal</dt><dd>{example.signal.replaceAll("_", " ")}</dd></div><div><dt>Rule baseline</dt><dd>{example.baseline}</dd></div><div><dt>Rule outcome</dt><dd>{example.ruleOutcome}</dd></div></dl><p className="c2-example__explanation"><strong>Why:</strong> {example.explanation}</p><p className="c2-source">{example.source}</p></article>)}</div><EvidenceLink /></section>;
}

function ComparisonPanel() {
  const [index, setIndex] = useState("0");
  const comparison = comparisons[Number(index)];
  return <section id="c2-methods" className="c2-stack c2-section" aria-labelledby="c2-methods-title"><div className="c2-section-heading"><div><span className="c2-kicker">D · Research design improvements</span><h2 id="c2-methods-title">Why the revised methodology is more defensible</h2><p>Compare each earlier decision with the corrected method and its research consequence.</p></div></div><Card><div className="c2-stack"><Select id="c2-comparison" label="Compare methodology" value={index} onChange={setIndex} options={comparisons.map((item, i) => ({ value: String(i), label: item.title }))} /><div className="c2-two" aria-live="polite"><div className="c2-inset"><span className="c2-kicker">Earlier approach</span><p>{comparison.before}</p></div><div className="c2-inset c2-inset--revised"><span className="c2-kicker">Revised approach / plan</span><p>{comparison.after}</p></div></div><p><strong>Why this matters:</strong> {comparison.why}</p></div></Card></section>;
}

function FuturePanel() {
  const [selected, setSelected] = useState(1);
  return <section id="c2-pipeline" className="c2-stack c2-section" aria-labelledby="c2-pipeline-title"><div className="c2-section-heading"><div><span className="c2-kicker">E · Analytical pipeline</span><h2 id="c2-pipeline-title">From multilingual comments to content-gap evidence</h2><p>Each stage of the analytical pipeline and its current status.</p></div></div><Card><div className="c2-stack"><ol className="c2-pipeline">{futurePipeline.map((step, index) => <li key={step.name}><button type="button" aria-pressed={selected === index} onClick={() => setSelected(index)}><span className="c2-pipeline__number">{index + 1}</span><b>{step.name}</b><Badge tone={step.status === "Implemented" ? "ok" : step.status === "Partial" ? "warn" : "neutral"}>{step.status}</Badge></button></li>)}</ol><div className="c2-explanation" aria-live="polite"><strong>{futurePipeline[selected].name}</strong><p>{futurePipeline[selected].detail}</p></div><Fold title="How JSD is interpreted" hint="Method"><div className="c2-stack"><p>For aligned topic distributions P (demand) and Q (supply), let M = (P + Q) / 2.</p><p className="c2-formula">JSD(P, Q) = ½ KL(P ‖ M) + ½ KL(Q ‖ M)</p><p>JSD is symmetric: it summarizes overall mismatch without identifying an undersupplied topic. Directional interpretation compares P(topic) − Q(topic) and pairs each topic with its explicit request count before suggesting an opportunity.</p><p className="provenance">With base-2 logarithms, JSD ranges from 0 to 1. SciPy's function returns its square-root distance. <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html" target="_blank" rel="noreferrer">SciPy definition ↗</a></p></div></Fold></div></Card></section>;
}

export function Component2Page() {
  return <div className="c2-page">
    <header className="c2-hero"><div className="c2-hero__body"><p className="c2-kicker">J26-DS-334 · Research progress · Evidence as of {EVIDENCE_DATE}</p><h1>{COMPONENT_TITLE}</h1><p>Identify genuine multilingual audience content demands, model audience demand and channel content supply in a shared semantic topic space, and quantify gaps using Jensen–Shannon Divergence.</p><div className="c2-hero__actions"><Link className="button c2-methodology-cta" to="/component-2/methodology"><Icon name="flow" size={18} /> Open Methodology Explorer <span aria-hidden="true">→</span></Link></div><div className="c2-hero__tags"><Badge tone="ok">Corpus frozen</Badge><Badge tone="ok">Classifiers trained</Badge><Badge tone="ok">Supply topics modelled</Badge><Badge tone="warn">Gap analysis in progress</Badge></div></div><div className="c2-hero__aside"><Icon name="topic" size={30} /><strong>Demand topics and JSD</strong><span>Current milestone</span><p>Channel-specific demand topics compared with supply, validated season to season.</p></div></header>
    <nav className="c2-section-nav" aria-label="Component 2 sections">{[["overview", "Study overview"], ["progress", "Development stages"], ["examples", "Annotated examples"], ["methods", "Design comparisons"], ["pipeline", "Analysis pipeline"], ["questions", "Research Q&A"]].map(([id, label]) => <a key={id} href={`#c2-${id}`}>{label}</a>)}</nav>
    <StatGrid label="Component 2 evidence snapshot"><StatCard label="Comments collected" value={number(corpus.comments)} hint={`${corpus.channels} Derana channels · ${corpus.months} months`} /><StatCard label="Labelled comments" value={number(annotationBatch.rows + calibration.total)} hint={`${annotationBatch.yes + calibration.yes} actionable requests`} /><StatCard label="Best classifier F1" value={bestClassifier.f1.toFixed(2)} hint={`vs ${bestClassifier.ruleF1.toFixed(2)} for keyword rules`} tone="ok" /><StatCard label="Supply topic coherence" value={supplyTopics.bertopic.toFixed(3)} hint={`c_v · vs ${supplyTopics.lda.toFixed(3)} for LDA`} tone="ok" /></StatGrid>
    <section id="c2-overview" className="c2-stack c2-section" aria-labelledby="c2-overview-title"><div className="c2-section-heading"><div><span className="c2-kicker">A · Research purpose and current scope</span><h2 id="c2-overview-title">Research question, intended contribution and implementation boundary</h2><p>What the component studies, what it contributes and what has been built.</p></div></div><div className="c2-two"><Card title="The research problem"><div className="c2-stack"><p>Comment volume and sentiment do not tell a channel what to produce next. Praise, reactions and topical discussion may contain no requested content action. Even a question can seek information about an existing video.</p><p>Component 2 asks whether a comment contains a genuine content request, what it asks for and who should act. That verified demand can later be compared with the channel's actual content supply.</p></div></Card><Card title="Intended novelty"><div className="c2-stack"><p>An integrated framework that identifies genuine audience content demands from multilingual YouTube comments and compares them with existing channel content using a shared semantic topic representation.</p><p><strong>The novelty lies in the integrated demand-to-supply intelligence framework, rather than in inventing individual NLP algorithms or divergence measures.</strong></p></div></Card></div><Card title="Current implementation boundary"><div className="c2-two"><div className="c2-stack"><Badge tone="ok">Implemented / verified software</Badge><p>Collection, validation, multilingual preprocessing, the Streamlit annotation portal, rule screening, leakage audits, frozen partitions, the expanded 84k-comment corpus, 544 labelled comments, trained demand classifiers and supply topic modelling.</p></div><div className="c2-stack"><Badge tone="warn">In progress</Badge><p>Channel-specific demand topics, aligned demand and supply distributions, Jensen–Shannon Divergence with per-topic gaps, season-to-season validation and the final blind held-out evaluation.</p></div></div></Card><div className="c2-data-strip"><span><b>{number(corpus.videos)}</b> videos modelled</span><span><b>{number(corpus.trainingPool)}</b> training-pool comments</span><span><b>{number(corpus.expandedHeldOut + 311)}</b> held-out comments</span><span><b>0</b> duplicate comment IDs</span></div><p className="provenance">Channels: Dream Star, Derana 60 Plus, Derana Little Star, FM Derana, Ada Derana Sports, Lokaya Saha Lokayo, TV Derana and Ada Derana. Conservative normalization preserves original language and emoji; exact source text is retained separately from NFC text. <EvidenceLink /></p></section>
    <ResearchTimeline />
    <ExamplesPanel />
    <ComparisonPanel />
    <FuturePanel />
    <section id="c2-questions" className="c2-stack c2-section" aria-labelledby="c2-questions-title"><div className="c2-section-heading"><div><span className="c2-kicker">F · Key research questions</span><h2 id="c2-questions-title">Methodology questions and evidence-based answers</h2><p>Concise explanations of the research decisions and results.</p></div></div>{researchQuestions.map(([question, answer]) => <Fold key={question} title={question}><p className="c2-reading">{answer}</p>{question === "What is JSD?" && <p className="c2-source"><a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html" target="_blank" rel="noreferrer">SciPy mathematical definition ↗</a></p>}</Fold>)}</section>
    <footer className="c2-footer"><p><strong>Evidence and scope.</strong> Verified on {EVIDENCE_DATE}. This page uses curated aggregates and minimized excerpts; no private datasets or commenter identifiers are included.</p><EvidenceLink /></footer>
  </div>;
}
