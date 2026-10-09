import { ErrorState, Loading } from "../../../components/common/States";
import { Badge, Card, KeyValues, PageHeader, TableWrap } from "../../../components/common/ui";
import { useApi } from "../../../hooks/useApi";
import { API_BASE_URL } from "../../../services/apiClient";
import { date, label } from "../../../utils/format";
import { component3Api } from "../api";
import { useResearch } from "../ResearchContext";

export function StatusPage() {
  const health = useApi((s) => component3Api.health(s), []);
  const { status } = useResearch();
  return (
    <>
      <PageHeader title="System Status" description="API health and research pipeline readiness are reported separately." />
      <div className="grid grid--2">
        <Card title="API">
          {health.status === "loading" && <Loading label="Checking API…" />}
          {health.status === "error" && (
            <>
              <p><Badge tone="bad">Unreachable</Badge></p>
              <ErrorState error={health.error} onRetry={health.reload} />
            </>
          )}
          {health.status === "success" && (
            <KeyValues rows={[
              ["Health", <Badge key="h" tone="ok">Running</Badge>],
              ["Service", `${health.data.service} ${health.data.version}`],
              ["Checked", date(health.data.time)],
              ["Base URL", <code key="u">{API_BASE_URL}</code>],
            ]} />
          )}
          <p className="muted">A running API does not mean research artifacts exist; see the pipeline status.</p>
        </Card>
        <Card title="Research data">
          {status.status === "loading" && <Loading />}
          {status.status === "error" && <ErrorState error={status.error} onRetry={status.reload} />}
          {status.status === "success" && (
            <KeyValues rows={[
              ["Research data", <Badge key="r" tone={status.data.research_data === "available" ? "ok" : "bad"}>{label(status.data.research_data)}</Badge>],
              ["Snapshots", String(status.data.snapshots.length)],
              ["Latest snapshot", <code key="l">{status.data.latest_snapshot_id ?? "—"}</code>],
              ["Reported snapshot", <code key="s">{status.data.snapshot_id ?? "—"}</code>],
            ]} />
          )}
        </Card>
      </div>
      {status.status === "success" && status.data.artifacts.length > 0 && (
        <Card title="Pipeline artifacts">
          <TableWrap label="Pipeline artifacts">
            <table className="table">
              <thead>
                <tr><th scope="col">Artifact</th><th scope="col">Status</th><th scope="col">Runs</th><th scope="col">Latest</th><th scope="col">Stage</th></tr>
              </thead>
              <tbody>
                {status.data.artifacts.map((a) => (
                  <tr key={a.name}>
                    <td>{label(a.name)}</td>
                    <td><Badge tone={a.status === "available" ? "ok" : "neutral"}>{a.status === "available" ? "Available" : "Missing"}</Badge></td>
                    <td className="num">{a.count}</td>
                    <td><code>{a.latest_id ?? "—"}</code></td>
                    <td className="muted">{a.detail ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <p className="muted">{status.data.note}</p>
        </Card>
      )}
    </>
  );
}
