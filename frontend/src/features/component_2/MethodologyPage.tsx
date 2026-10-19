import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowNode } from "../../components/charts/FlowCanvas";
import { Icon } from "../../components/common/Icon";
import { Badge, Notice, Select, TableWrap, type Tone } from "../../components/common/ui";
import { calculateJsd } from "./jsd";
import {
  alignmentStrategies, decisionJourney, defenceQuestions, measureComparisons, methodEdges, methodNodes,
  modelApproaches, verifiedProgress, type MethodNode, type MethodStatus,
} from "./methodologyData";
import { COMPONENT_TITLE } from "./researchData";
import "./component2.css";
import "./methodology.css";

const statusTone: Record<MethodStatus, Tone> = {
  Completed: "ok", Preliminary: "warn", "In progress": "warn", Planned: "neutral",
};

const layout: Record<string, { x: number; y: number; w: number; h: number }> = {
  problem: { x: 560, y: 34, w: 360, h: 68 },
  collection: { x: 560, y: 142, w: 360, h: 68 },
  preprocessing: { x: 560, y: 250, w: 360, h: 68 },
  screening: { x: 90, y: 395, w: 440, h: 68 },
  annotation: { x: 90, y: 500, w: 440, h: 68 },
  "demand-model": { x: 90, y: 605, w: 440, h: 68 },
  "request-understanding": { x: 90, y: 710, w: 440, h: 68 },
  "demand-topics": { x: 90, y: 815, w: 440, h: 68 },
  "demand-distribution": { x: 90, y: 920, w: 440, h: 68 },
  "supply-metadata": { x: 950, y: 395, w: 440, h: 68 },
  "programme-context": { x: 950, y: 500, w: 440, h: 68 },
  "supply-topics": { x: 950, y: 605, w: 440, h: 68 },
  "supply-distribution": { x: 950, y: 710, w: 440, h: 68 },
  alignment: { x: 560, y: 1045, w: 360, h: 68 },
  jsd: { x: 560, y: 1153, w: 360, h: 68 },
  direction: { x: 560, y: 1261, w: 360, h: 68 },
  verification: { x: 560, y: 1369, w: 360, h: 68 },
  opportunities: { x: 560, y: 1477, w: 360, h: 68 },
  dashboard: { x: 560, y: 1585, w: 360, h: 68 },
};

const demandIds = new Set(["screening", "annotation", "demand-model", "request-understanding", "demand-topics", "demand-distribution"]);
const supplyIds = new Set(["supply-metadata", "programme-context", "supply-topics", "supply-distribution"]);
const foundationIds = new Set(["problem", "collection", "preprocessing"]);
const sharedIds = new Set(["alignment", "jsd", "direction", "verification", "opportunities", "dashboard"]);

function activeIds(selected: string) {
  if (demandIds.has(selected)) return new Set([...foundationIds, ...demandIds, ...sharedIds]);
  if (supplyIds.has(selected)) return new Set([...foundationIds, ...supplyIds, ...sharedIds]);
  if (sharedIds.has(selected)) return new Set([...foundationIds, ...demandIds, ...supplyIds, ...sharedIds]);
  return foundationIds;
}

function NodeCard({ node }: { node: MethodNode }) {
  return <div className="m2-flow-node"><span>{node.phase}</span><strong>{node.shortTitle}</strong><small>{node.status}</small></div>;
}

function MethodFlow({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const active = activeIds(selected);
  const nodes: FlowNode[] = methodNodes.map((node) => ({
    id: node.id, ...layout[node.id], content: <NodeCard node={node} />, label: `Open ${node.title}`,
    selected: node.id === selected, tone: node.status === "Completed" ? "ok" : node.status === "In progress" ? "accent" : node.status === "Preliminary" ? "accent" : "missing",
  }));
  const edges: FlowEdge[] = methodEdges.map(([from, to]) => ({
    from, to, color: active.has(from) && active.has(to) ? "#315fa1" : "#94a3b8",
    width: active.has(from) && active.has(to) ? 2.5 : 1.2, muted: !(active.has(from) && active.has(to)),
  }));
  return <>
    <FlowCanvas width={1480} height={1685} nodes={nodes} edges={edges} onSelect={onSelect} minScale={0.38}
      label="Selectable Component 2 methodology flowchart"
      lanes={[
        { id: "demand", title: "Path A - Audience demand", x: 38, y: 350, w: 550, h: 675 },
        { id: "supply", title: "Path B - Content supply", x: 892, y: 350, w: 550, h: 570 },
      ]} />
    <FlowLegend items={[
      { kind: "dot", tone: "ok", label: "Completed software/evidence" },
      { kind: "dot", tone: "accent", label: "Preliminary" },
      { kind: "dot", tone: "failed", label: "Blocked by a research prerequisite" },
      { kind: "dot", tone: "missing", label: "Planned" },
    ]} />
  </>;
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

function NodeDetail({ node, onSelect }: { node: MethodNode; onSelect: (id: string) => void }) {
  const index = methodNodes.findIndex((item) => item.id === node.id);
  return <aside className="m2-detail" aria-live="polite" aria-labelledby="m2-detail-title">
    <header><div><span className="m2-eyebrow">{node.phase}</span><h3 id="m2-detail-title">{node.title}</h3></div><Badge tone={statusTone[node.status]}>{node.status}</Badge></header>
    <p className="m2-detail__lead">{node.simpleExplanation}</p>
    <dl className="m2-detail__grid">
      <DetailRow label="Purpose">{node.purpose}</DetailRow>
      <DetailRow label="Input">{node.input}</DetailRow>
      <DetailRow label="Method">{node.method}</DetailRow>
      <DetailRow label="Why necessary">{node.whyNecessary}</DetailRow>
      <DetailRow label="Alternative methods"><ul>{node.alternatives.map((item) => <li key={item}>{item}</li>)}</ul></DetailRow>
      <DetailRow label="Method selection">{node.selection}</DetailRow>
      <DetailRow label="Output">{node.output}</DetailRow>
      <DetailRow label="Illustrative example">{node.example}</DetailRow>
      <DetailRow label="Evaluation">{node.evaluation}</DetailRow>
      <DetailRow label="Verified status">{node.evidence}</DetailRow>
      <DetailRow label="Limitations">{node.limitations}</DetailRow>
    </dl>
    <details className="m2-defence-note"><summary>Research defence explanation</summary><div><p><strong>Technical explanation:</strong> {node.technicalExplanation}</p><p><strong>Likely question:</strong> {node.lecturerQuestion}</p><p><strong>Defensible answer:</strong> {node.modelAnswer}</p><p><strong>Avoid:</strong> {node.avoidAnswer}</p></div></details>
    <nav className="m2-detail__pager" aria-label="Methodology step navigation">
      <button type="button" disabled={index === 0} onClick={() => onSelect(methodNodes[index - 1].id)}>Previous method</button>
      <button type="button" disabled={index === methodNodes.length - 1} onClick={() => onSelect(methodNodes[index + 1].id)}>Next method</button>
    </nav>
  </aside>;
}

function ModelExplorer() {
  const [selected, setSelected] = useState("rules");
  const approach = modelApproaches.find((item) => item.id === selected) ?? modelApproaches[0];
  return <section id="m2-models" className="m2-section" aria-labelledby="m2-models-title">
    <div className="m2-section-heading"><span className="m2-index">02</span><div><p className="m2-eyebrow">Demand extraction alternatives</p><h2 id="m2-models-title">Compare models before selecting complexity</h2><p>These are candidate experiments, not interchangeable claims of success.</p></div></div>
    <div className="m2-model-layout">
      <div className="m2-model-tabs" role="tablist" aria-label="Demand extraction approaches">{modelApproaches.map((item) => <button type="button" role="tab" aria-selected={item.id === selected} key={item.id} onClick={() => setSelected(item.id)}>{item.name}<small>{item.role}</small></button>)}</div>
      <div className="m2-model-detail" role="tabpanel"><span className="m2-eyebrow">{approach.role}</span><h3>{approach.name}</h3><dl><div><dt>Why investigate it</dt><dd>{approach.strengths}</dd></div><div><dt>Risk or limitation</dt><dd>{approach.limits}</dd></div><div><dt>Current evidence</dt><dd>{approach.evidence}</dd></div></dl></div>
    </div>
    <div className="m2-evaluation-strip"><strong>Model-selection evidence</strong><span>Precision / recall / F1</span><span>PR-AUC</span><span>Video-grouped validation</span><span>Script/language subgroups</span><span>Held-out testing</span><span>Agreement and label sufficiency</span></div>
  </section>;
}

function AlignmentExplorer() {
  const [selected, setSelected] = useState(0);
  return <section id="m2-alignment" className="m2-section" aria-labelledby="m2-alignment-title">
    <div className="m2-section-heading"><span className="m2-index">03</span><div><p className="m2-eyebrow">Comparable topic distributions</p><h2 id="m2-alignment-title">Demand and supply need one semantic coordinate system</h2><p>Two independently named clusters are not automatically comparable.</p></div></div>
    <div className="m2-alignment"><div className="m2-domain m2-domain--demand"><Icon name="comment" size={24} /><strong>Verified audience requests</strong><span>Short, multilingual, action-oriented text</span></div><div className="m2-alignment__center"><span>Validated shared topics</span><strong>Same dimensions</strong><span>Same channel and time window</span></div><div className="m2-domain m2-domain--supply"><Icon name="play" size={24} /><strong>Published video supply</strong><span>Titles, descriptions, format and programme context</span></div></div>
    <div className="m2-strategy-grid">{alignmentStrategies.map((strategy, index) => <button type="button" key={strategy.name} aria-pressed={selected === index} onClick={() => setSelected(index)}><span>Strategy {String.fromCharCode(65 + index)}</span><strong>{strategy.name}</strong></button>)}</div>
    <div className="m2-strategy-detail" aria-live="polite"><p><strong>Advantage:</strong> {alignmentStrategies[selected].benefit}</p><p><strong>Validation risk:</strong> {alignmentStrategies[selected].risk}</p></div>
    <Notice>Demand and supply share the pinned multilingual e5 embedding space; topics are judged by coherence, interpretability and stability across comment and video text.</Notice>
  </section>;
}

const initialTopics = [
  { name: "Physics", demand: 50, supply: 10 },
  { name: "Chemistry", demand: 30, supply: 70 },
  { name: "Mathematics", demand: 20, supply: 20 },
];

function pct(value: number) { return `${(value * 100).toFixed(1)}%`; }
function bits(value: number) { return `${value.toFixed(4)} bits`; }

function JsdExplorer() {
  const [topics, setTopics] = useState(initialTopics);
  const calculated = useMemo(() => {
    try { return { result: calculateJsd(topics.map((topic) => topic.demand), topics.map((topic) => topic.supply)), error: "" }; }
    catch (error) { return { result: null, error: error instanceof Error ? error.message : "Invalid distribution." }; }
  }, [topics]);
  const setValue = (index: number, side: "demand" | "supply", value: number) => setTopics((current) => current.map((topic, i) => i === index ? { ...topic, [side]: Number.isFinite(value) ? Math.max(0, value) : 0 } : topic));
  const scenario = (kind: "default" | "identical" | "supply") => {
    if (kind === "default") setTopics(initialTopics);
    if (kind === "identical") setTopics(initialTopics.map((topic) => ({ ...topic, demand: [40, 35, 25][initialTopics.indexOf(topic)], supply: [40, 35, 25][initialTopics.indexOf(topic)] })));
    if (kind === "supply") setTopics([{ name: "Physics", demand: 20, supply: 65 }, { name: "Chemistry", demand: 45, supply: 20 }, { name: "Mathematics", demand: 35, supply: 15 }]);
  };
  const result = calculated.result;
  return <section id="m2-jsd" className="m2-section m2-jsd" aria-labelledby="m2-jsd-title">
    <div className="m2-section-heading"><span className="m2-index">04</span><div><p className="m2-eyebrow">Why Jensen-Shannon Divergence?</p><h2 id="m2-jsd-title">Global mismatch, local contribution and direction are different quantities</h2><p>Adjust the hypothetical weights. The calculator normalizes each side before computing base-2 divergence.</p></div></div>
    <div className="m2-formula-grid"><div><span>Midpoint</span><strong>M = (D + S) / 2</strong></div><div><span>Demand to midpoint</span><strong>KL(D || M)</strong></div><div><span>Supply to midpoint</span><strong>KL(S || M)</strong></div><div><span>Global divergence</span><strong>JSD = 1/2 KL(D || M) + 1/2 KL(S || M)</strong></div></div>
    <div className="m2-scenario-buttons" aria-label="Hypothetical JSD scenarios"><button type="button" onClick={() => scenario("default")}>Demand/supply mismatch</button><button type="button" onClick={() => scenario("identical")}>Identical distributions</button><button type="button" onClick={() => scenario("supply")}>Supply-heavy topic</button></div>
    <div className="m2-jsd-workbench">
      <div className="m2-jsd-inputs"><h3>Hypothetical topic weights</h3>{topics.map((topic, index) => <fieldset key={topic.name}><legend>{topic.name}</legend><label>Demand weight<input aria-label={`Demand ${topic.name}`} type="number" min="0" step="1" value={topic.demand} onChange={(event) => setValue(index, "demand", Number(event.target.value))} /></label><label>Supply weight<input aria-label={`Supply ${topic.name}`} type="number" min="0" step="1" value={topic.supply} onChange={(event) => setValue(index, "supply", Number(event.target.value))} /></label></fieldset>)}</div>
      <div className="m2-jsd-result" aria-live="polite">{result ? <><span>Overall descriptive mismatch</span><strong>{bits(result.divergence)}</strong><div className="m2-jsd-meter"><i style={{ width: `${result.divergence * 100}%` }} /></div><p>{result.divergence < 1e-10 ? "The aligned proportions are identical. This does not prove every request is satisfied." : "A positive JSD means the overall aligned topic proportions differ. It does not prove unmet demand."}</p><dl><div><dt>KL(D || M)</dt><dd>{bits(result.klDemandToMidpoint)}</dd></div><div><dt>KL(S || M)</dt><dd>{bits(result.klSupplyToMidpoint)}</dd></div><div><dt>Range</dt><dd>0 to 1 bit</dd></div></dl></> : <p className="m2-error">{calculated.error}</p>}</div>
    </div>
    {result && <><div className="m2-bars" aria-label="Normalized demand and supply distributions">{topics.map((topic, index) => <div className="m2-bar-row" key={topic.name}><strong>{topic.name}</strong><div><span>Demand {pct(result.demand[index])}</span><i className="m2-bar m2-bar--demand" style={{ width: pct(result.demand[index]) }} /></div><div><span>Supply {pct(result.supply[index])}</span><i className="m2-bar m2-bar--supply" style={{ width: pct(result.supply[index]) }} /></div></div>)}</div>
      <TableWrap label="JSD topic calculations"><table className="table m2-jsd-table"><thead><tr><th>Topic</th><th>D</th><th>S</th><th>M</th><th>D - S</th><th>Direction</th><th>JSD contribution</th></tr></thead><tbody>{topics.map((topic, index) => { const row = result.topics[index]; return <tr key={topic.name}><th>{topic.name}</th><td>{pct(row.demand)}</td><td>{pct(row.supply)}</td><td>{pct(row.midpoint)}</td><td>{row.signedDifference >= 0 ? "+" : ""}{pct(row.signedDifference)}</td><td>{Math.abs(row.signedDifference) < 1e-10 ? "Balanced share" : row.signedDifference > 0 ? "Demand-heavy" : "Supply-heavy"}</td><td>{bits(row.jsdContribution)}</td></tr>; })}</tbody></table></TableWrap></>}
    <div className="m2-interpretation"><div><span>Question 1</span><strong>How different overall?</strong><p>Use global JSD across the complete aligned distributions.</p></div><div><span>Question 2</span><strong>Where is demand relatively higher?</strong><p>Use signed D - S with local JSD contributions and uncertainty.</p></div><div><span>Question 3</span><strong>Is the need genuinely unmet?</strong><p>Use request evidence, catalogue matching and human verification. JSD cannot answer this alone.</p></div></div>
    <h3 className="m2-subheading">JSD and alternative measures</h3><div className="m2-measures">{measureComparisons.map((measure) => <details key={measure.name}><summary>{measure.name}<span>{measure.role}</span></summary><dl><div><dt>Question</dt><dd>{measure.question}</dd></div><div><dt>Captures</dt><dd>{measure.captures}</dd></div><div><dt>Misses</dt><dd>{measure.misses}</dd></div></dl></details>)}</div>
    <div className="m2-sources"><strong>Mathematical references</strong><a href="https://ieeexplore.ieee.org/document/61115" target="_blank" rel="noreferrer">Lin (1991), IEEE: divergence measures based on Shannon entropy</a><a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html" target="_blank" rel="noreferrer">SciPy definition: jensenshannon returns the square-root distance</a></div>
  </section>;
}

function DecisionExplorer() {
  const [selected, setSelected] = useState(0);
  return <section id="m2-decision" className="m2-section" aria-labelledby="m2-decision-title">
    <div className="m2-section-heading"><span className="m2-index">05</span><div><p className="m2-eyebrow">From audience request to content opportunity</p><h2 id="m2-decision-title">A distribution score never replaces evidence verification</h2><p>An illustrative request traced through every stage of the method.</p></div></div>
    <div className="m2-journey"><ol>{decisionJourney.map(([title], index) => <li key={title}><button type="button" aria-current={selected === index ? "step" : undefined} onClick={() => setSelected(index)}><span>{index + 1}</span>{title}</button></li>)}</ol><div className="m2-journey__detail"><span>Hypothetical step {selected + 1}</span><h3>{decisionJourney[selected][0]}</h3><p>{decisionJourney[selected][1]}</p>{selected === 0 && <blockquote>"Please upload the full audition performance, not only highlights."</blockquote>}</div></div>
    <div className="m2-concept-dashboard"><header><div><span>Illustrative planning view</span><strong>Channel and period would be selected here</strong></div><Badge tone="neutral">Illustrative example</Badge></header><div className="m2-concept-grid"><div><span>Global JSD</span><strong>Calculated from aligned distributions</strong><small>Overall mismatch only</small></div><div><span>Directional topics</span><strong>D - S with contribution</strong><small>Relative share, not proof of absence</small></div><div><span>Request evidence</span><strong>Action, format and target</strong><small>Linked to source context</small></div><div><span>Coverage status</span><strong>Verified / possible / unknown</strong><small>Catalogue and human review</small></div></div></div>
  </section>;
}

function NoveltyAndDefence() {
  const [question, setQuestion] = useState(defenceQuestions[0].id);
  const current = defenceQuestions.find((item) => item.id === question) ?? defenceQuestions[0];
  return <>
    <section id="m2-novelty" className="m2-section" aria-labelledby="m2-novelty-title"><div className="m2-section-heading"><span className="m2-index">06</span><div><p className="m2-eyebrow">Research contribution</p><h2 id="m2-novelty-title">Intended Novelty</h2></div></div><div className="m2-novelty-statement"><p>The proposed contribution is an integrated framework that identifies genuine audience content demands from multilingual YouTube comments and compares them with existing channel content using a shared semantic topic representation.</p><p>By combining multilingual demand extraction, content-supply modelling, Jensen-Shannon Divergence and topic-level gap interpretation, the framework aims to identify measurable, evidence-supported content opportunities for multi-channel media organizations.</p><p><strong>The novelty lies in the integrated demand-to-supply intelligence framework, rather than in inventing individual NLP algorithms or divergence measures.</strong> Its reliability and practical usefulness are assessed through classifier evaluation, topic coherence and season-to-season validation.</p></div></section>
    <section id="m2-defence" className="m2-section" aria-labelledby="m2-defence-title"><div className="m2-section-heading"><span className="m2-index">07</span><div><p className="m2-eyebrow">Research evaluation Q&A</p><h2 id="m2-defence-title">Explain each methodological decision precisely</h2><p>Choose a question for a concise explanation, defensible answer and common mistake.</p></div></div><Select id="m2-defence-question" label="Research question" value={question} onChange={setQuestion} options={defenceQuestions.map((item) => ({ value: item.id, label: item.title }))} /><div className="m2-answer"><span>20-second explanation</span><h3>{current.title}</h3><p>{current.simple}</p><div><section><strong>Defensible answer</strong><p>{current.answer}</p></section><section><strong>Common incorrect answer</strong><p>{current.avoid}</p></section></div></div></section>
  </>;
}

export function MethodologyPage() {
  const [selectedNode, setSelectedNode] = useState("problem");
  const node = methodNodes.find((item) => item.id === selectedNode) ?? methodNodes[0];
  return <div className="m2-page">
    <header className="m2-hero"><div><p className="m2-eyebrow">J26-DS-334 · Component methodology</p><h1>{COMPONENT_TITLE}</h1><p>Explore how the complete proposed research works, why each method is needed and what evidence would be required to validate its usefulness.</p><div className="m2-hero__actions"><Link className="button" to="/component-2">View Research Progress</Link><a className="button" href="#m2-flow">Start with the methodology flow</a></div></div><aside><Icon name="flow" size={30} /><strong>Proposed architecture</strong><p>Planned stages are clearly separated from verified implementation evidence.</p></aside></header>
    <nav className="c2-section-nav m2-section-nav" aria-label="Methodology Explorer sections">{[["flow", "Method flow"], ["models", "Demand models"], ["alignment", "Topic alignment"], ["jsd", "JSD explorer"], ["decision", "Decision path"], ["novelty", "Research novelty"], ["defence", "Research Q&A"]].map(([id, label]) => <a key={id} href={`#m2-${id}`}>{label}</a>)}</nav>
    <section className="m2-boundary" aria-label="Page purpose"><div><strong>Research Progress</strong><p>What has been implemented and verified?</p><Link to="/component-2">Open the separate progress page</Link></div><div className="is-current"><strong>Methodology Explorer</strong><p>How should the complete proposed research work and be evaluated?</p><span>Current page</span></div></section>
    <section id="m2-flow" className="m2-section" aria-labelledby="m2-flow-title"><div className="m2-section-heading"><span className="m2-index">01</span><div><p className="m2-eyebrow">End-to-end research architecture</p><h2 id="m2-flow-title">Follow both analytical paths before they merge</h2><p>Select any stage to inspect its purpose, alternatives, evaluation and current evidence.</p></div></div><div className="m2-flow-layout"><div><MethodFlow selected={selectedNode} onSelect={setSelectedNode} /></div><NodeDetail node={node} onSelect={setSelectedNode} /></div></section>
    <section className="m2-progress-map" aria-labelledby="m2-progress-map-title"><div><p className="m2-eyebrow">Proposed method versus verified progress</p><h2 id="m2-progress-map-title">Logical architecture is not the experiment timeline</h2></div><ol>{verifiedProgress.map(([title, status, detail]) => <li key={title}><Badge tone={statusTone[status as MethodStatus]}>{status}</Badge><strong>{title}</strong><p>{detail}</p></li>)}</ol></section>
    <ModelExplorer />
    <AlignmentExplorer />
    <JsdExplorer />
    <DecisionExplorer />
    <NoveltyAndDefence />
    <footer className="m2-footer"><p><strong>How to read this page:</strong> the examples and calculator explain the method; measured results are reported on the Research Progress page.</p></footer>
  </div>;
}
