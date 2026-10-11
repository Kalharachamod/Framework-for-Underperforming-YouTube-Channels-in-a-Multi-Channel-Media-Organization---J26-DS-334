import { Link } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, Notice, PageHeader, StatCard, StatGrid } from "../../../components/common/ui";
import { date, int, num } from "../../../utils/format";
import { LIMITATIONS, Provenance } from "../ContextBar";
import { useResearch } from "../ResearchContext";

const ARTIFACT_LABELS: Record<string, string> = {
  baseline_louvain: "Louvain baseline",
  baseline_node2vec: "node2vec baseline",
  evaluations: "Evaluation (STEP 21)",
  explanations: "Explanations (STEP 22)",
};

export function OverviewPage() {
  const { status, experiments, channels } = useResearch();
  if (status.status === "loading" || status.status === "idle") return <Loading label="Loading research status…" />;
  if (status.status === "error") return <ErrorState error={status.error} onRetry={status.reload} />;
  const s = status.data;
  if (s.research_data === "missing") {
    return (
      <>
        <PageHeader title="Overview" />
        <EmptyState title="No research data yet">
          <p>No research snapshot exists. Run the collection pipeline and create a research snapshot first.</p>
        </EmptyState>
      </>
    );
  }
  const snap = s.snapshots.find((x) => x.snapshot_id === s.snapshot_id);
  const exp = experiments.status === "success" ? experiments.data.items[0] : undefined;
  const shown = s.artifacts.filter((a) => a.name in ARTIFACT_LABELS);
  const extracted = date(snap?.extracted_at ?? snap?.created_at); // "YYYY-MM-DD HH:MM UTC" or "—"

  return (
    <>
      <PageHeader title="Overview" description="What the research pipeline has produced for the selected snapshot." />
      <StatGrid label="Snapshot summary">
        <StatCard label="Extracted" value={extracted === "—" ? "—" : extracted.slice(0, 10)} hint={extracted === "—" ? undefined : extracted.slice(11)} />
        <StatCard label="Channels" value={int(snap?.channels)} />
        <StatCard label="Videos" value={int(snap?.videos)} />
        <StatCard label="Comments" value={int(snap?.comments)} hint="public, within collection limits" />
        <StatCard label="Scored pairs" value={exp ? int(exp.scored_pairs) : "—"} hint={exp ? `of ${int(exp.pairs)} ordered pairs` : "no scoring run"} />
      </StatGrid>
      <Notice>{LIMITATIONS}</Notice>
      <div className="grid grid--wide-left">
        <Card title="Scoring experiment">
          {experiments.status === "loading" && <Loading />}
          {experiments.status === "error" && <ErrorState error={experiments.error} />}
          {experiments.status === "success" && !exp && (
            <EmptyState title="No Audience Bridge Score run">
              <p>Run python -m research.component_3.model.audience_bridge for this snapshot.</p>
            </EmptyState>
          )}
          {exp && (
            <KeyValues
              rows={[
                ["Latest experiment", <code key="e">{exp.experiment_id}</code>],
                ["Weights", `diffusion ${num(exp.w_diffusion)} · embedding ${num(exp.w_embedding)} · topic ${num(exp.w_topic)}`],
                ["Embeddings", exp.w_embedding > 0 ? `${exp.embedding_source}${exp.embedding_experiment_id ? ` (${exp.embedding_experiment_id})` : ""}` : "not used"],
                ["Confidence k", String(exp.confidence_k)],
                ["Formula", exp.provisional ? <Badge key="p" tone="warn">Provisional</Badge> : <Badge key="p" tone="ok">Confirmed</Badge>],
                ["Explanations", exp.explanation_ids.length ? exp.explanation_ids.join(", ") : "none"],
                ["Evaluations", exp.evaluation_ids.length ? exp.evaluation_ids.join(", ") : "none"],
              ]}
            />
          )}
        </Card>
        <Card title="Analysis artifacts">
          <ul className="artifact-list">
            {shown.map((a) => (
              <li key={a.name}>
                <span>{ARTIFACT_LABELS[a.name]}</span>
                <Badge tone={a.status === "available" ? "ok" : "neutral"}>{a.status === "available" ? "Available" : "Missing"}</Badge>
                <span className="muted">{a.latest_id ?? ""}</span>
              </li>
            ))}
          </ul>
          <KeyValues rows={[["Snapshot", <code key="s">{s.snapshot_id}</code>], ["Snapshots available", int(s.snapshots.length)]]} />
          <p className="muted">
            Full per-artifact status: <Link to="/status">System status</Link>.
          </p>
        </Card>
      </div>
      <Card title="Explore">
        {channels.status === "loading" && <Loading />}
        {channels.status === "error" && <ErrorState error={channels.error} />}
        {channels.status === "success" && (
          <>
            <p className="muted" style={{ marginBottom: 12 }}>{channels.data.items.length} research channels in this snapshot.</p>
            <div className="link-cards">
              <Link className="link-card" to="/bridges"><strong>Audience Bridges</strong>Ranked destinations for a source channel</Link>
              <Link className="link-card" to="/channels"><strong>Channel Explorer</strong>Metadata, features and shared commenters</Link>
              <Link className="link-card" to="/explainability"><strong>Explainability</strong>Why a pair received its score</Link>
              <Link className="link-card" to="/evaluation"><strong>Evaluation</strong>Agreement with baselines and robustness</Link>
            </div>
          </>
        )}
      </Card>
      <Provenance snapshotId={s.snapshot_id} experimentId={exp?.experiment_id ?? null} />
    </>
  );
}
