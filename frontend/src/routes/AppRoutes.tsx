import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell, type NavItem } from "../components/layout/AppShell";
import { ContextBar } from "../features/component_3/ContextBar";
import { BridgesPage } from "../features/component_3/pages/BridgesPage";
import { ChannelExplorerPage } from "../features/component_3/pages/ChannelExplorerPage";
import { DashboardPage } from "../features/component_3/pages/DashboardPage";
import { EvaluationPage } from "../features/component_3/pages/EvaluationPage";
import { ExperimentsPage } from "../features/component_3/pages/ExperimentsPage";
import { ExplainabilityPage } from "../features/component_3/pages/ExplainabilityPage";
import { GraphPage } from "../features/component_3/pages/GraphPage";
import { PipelinePage } from "../features/component_3/pages/PipelinePage";
import { OverviewPage } from "../features/component_3/pages/OverviewPage";
import { StatusPage } from "../features/component_3/pages/StatusPage";
import { TopicsPage } from "../features/component_3/pages/TopicsPage";
import { ResearchProvider, useResearch } from "../features/component_3/ResearchContext";
import { ChannelSearch } from "../features/component_3/TrackedChannels";

export const NAV: NavItem[] = [
  { to: "/", label: "Overview", group: "Insights", icon: "dashboard" },
  { to: "/bridges", label: "Audience Bridges", group: "Insights", icon: "bridges" },
  { to: "/channels", label: "Channel Explorer", group: "Insights", icon: "channels" },
  { to: "/pipeline", label: "Pipeline Graph", group: "Research", icon: "flow" },
  { to: "/graph", label: "Graph Intelligence", group: "Research", icon: "graph" },
  { to: "/topics", label: "Topic Intelligence", group: "Research", icon: "topic" },
  { to: "/evaluation", label: "Baselines & Evaluation", group: "Research", icon: "evaluation" },
  { to: "/explainability", label: "Explainability", group: "Research", icon: "explain" },
  { to: "/experiments", label: "Experiments", group: "Research", icon: "overview" },
  { to: "/status", label: "System Status", group: "System", icon: "status" },
];

/** Top bar: current page title, snapshot/experiment selectors, channel search and live status (from /status). */
function TopBar() {
  const { pathname } = useLocation();
  const { status } = useResearch();
  const title = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to)))?.label ?? (pathname.startsWith("/overview") ? "Research Overview" : "Overview");
  const api = status.status === "success" ? "Connected" : status.status === "error" ? "Unreachable" : "Checking";
  const data = status.status === "success" ? (status.data.research_data === "available" ? "Available" : "Missing") : "—";
  return (
    <div className="topbar__row">
      <span className="topbar__title">{title}</span>
      <ContextBar />
      <div className="topbar__end">
        <ChannelSearch />
        <span role="group" aria-label="Live status" className="topbar__statuses">
          <span className={`topbar__status${api === "Connected" ? " is-ok" : ""}`}>API <strong>{api}</strong></span>
          <span className={`topbar__status${data === "Available" ? " is-ok" : ""}`}>Research data <strong>{data}</strong></span>
        </span>
      </div>
    </div>
  );
}

export function AppRoutes() {
  return (
    <ResearchProvider>
      <AppShell nav={NAV} header={<TopBar />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/bridges" element={<BridgesPage />} />
          <Route path="/channels" element={<ChannelExplorerPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/explainability" element={<ExplainabilityPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/topics" element={<TopicsPage />} />
          <Route path="/experiments" element={<ExperimentsPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </ResearchProvider>
  );
}
