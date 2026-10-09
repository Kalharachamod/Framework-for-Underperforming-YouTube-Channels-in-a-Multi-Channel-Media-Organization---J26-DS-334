import { Link } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, Notice, PageHeader } from "../../../components/common/ui";
import { date, int } from "../../../utils/format";
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

  return (
    <>
      <PageHeader title="Overview" description="Diffusion-Based Cross-Channel Audience Bridge Scoring: what the research pipeline has produced." />
      <Notice>{LIMITATIONS}</Notice>
      <div className="grid grid--2">
        <Card title="Research snapshot">
          <KeyValues
            rows={[
              ["Snapshot", <code key="s">{s.snapshot_id}</code>],
              ["Extracted", date(snap?.extracted_at ?? snap?.created_at)],
              ["Channels", int(snap?.channels)],
              ["Videos", int(snap?.videos)],
              ["Comments", int(snap?.comments)],
              ["Snapshots available", int(s.snapshots.length)],
            ]}
          />
        </Card>
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
                ["Weights", `diffusion ${exp.w_diffusion} · topic ${exp.w_topic}`],
                ["Confidence k", String(exp.confidence_k)],
                ["Scored pairs", `${int(exp.scored_pairs)} of ${int(exp.pairs)}`],
                ["Formula", exp.provisional ? <Badge key="p" tone="warn">Provisional</Badge> : <Badge key="p" tone="ok">Confirmed</Badge>],
                ["Explanations", exp.explanation_ids.length ? exp.explanation_ids.join(", ") : "none"],
                ["Evaluations", exp.evaluation_ids.length ? exp.evaluation_ids.join(", ") : "none"],
              ]}
            />
          )}
        </Card>
      </div>
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
        <p className="muted">
          Full per-artifact status: <Link to="/status">System status</Link>.
        </p>
      </Card>
      <Card title="Channels">
        {channels.status === "loading" && <Loading />}
        {channels.status === "error" && <ErrorState error={channels.error} />}
        {channels.status === "success" && (
          <p>
            {channels.data.items.length} research channels in this snapshot.{" "}
            <Link to="/bridges">Explore audience bridges</Link> or <Link to="/channels">inspect a channel</Link>.
          </p>
        )}
      </Card>
      <Provenance snapshotId={s.snapshot_id} experimentId={exp?.experiment_id ?? null} />
    </>
  );
}
