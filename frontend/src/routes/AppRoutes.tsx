import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Loading } from "../components/common/States";
import { AppShell, type NavItem } from "../components/layout/AppShell";
import { ContextBar } from "../features/component_3/ContextBar";
import { BridgesPage } from "../features/component_3/pages/BridgesPage";
import { DashboardPage } from "../features/component_3/pages/DashboardPage";
import { ResearchProvider, useResearch } from "../features/component_3/ResearchContext";
import { ChannelSearch } from "../features/component_3/TrackedChannels";

// Secondary pages load on first visit; Overview and Audience Bridges ship in the main bundle.
const ChannelExplorerPage = lazy(() => import("../features/component_3/pages/ChannelExplorerPage").then((m) => ({ default: m.ChannelExplorerPage })));
const EvaluationPage = lazy(() => import("../features/component_3/pages/EvaluationPage").then((m) => ({ default: m.EvaluationPage })));
const ExperimentsPage = lazy(() => import("../features/component_3/pages/ExperimentsPage").then((m) => ({ default: m.ExperimentsPage })));
const ExplainabilityPage = lazy(() => import("../features/component_3/pages/ExplainabilityPage").then((m) => ({ default: m.ExplainabilityPage })));
const GraphPage = lazy(() => import("../features/component_3/pages/GraphPage").then((m) => ({ default: m.GraphPage })));
const NeuralPage = lazy(() => import("../features/component_3/pages/NeuralPage").then((m) => ({ default: m.NeuralPage })));
const PipelinePage = lazy(() => import("../features/component_3/pages/PipelinePage").then((m) => ({ default: m.PipelinePage })));
const OverviewPage = lazy(() => import("../features/component_3/pages/OverviewPage").then((m) => ({ default: m.OverviewPage })));
const StatusPage = lazy(() => import("../features/component_3/pages/StatusPage").then((m) => ({ default: m.StatusPage })));
const TopicsPage = lazy(() => import("../features/component_3/pages/TopicsPage").then((m) => ({ default: m.TopicsPage })));

export const NAV: NavItem[] = [
  { to: "/", label: "Overview", group: "Core workspace", icon: "dashboard" },
  { to: "/bridges", label: "Audience Bridges", group: "Core workspace", icon: "bridges" },
  { to: "/channels", label: "Channel Explorer", group: "Core workspace", icon: "channels" },
  { to: "/pipeline", label: "Pipeline Graph", group: "Research models", icon: "flow" },
  { to: "/graph", label: "Graph Intelligence", group: "Research models", icon: "graph" },
  { to: "/neural", label: "Neural Models", group: "Research models", icon: "neural" },
  { to: "/topics", label: "Topic Intelligence", group: "Research models", icon: "topic" },
  { to: "/evaluation", label: "Baselines & Evaluation", group: "Validation", icon: "evaluation" },
  { to: "/explainability", label: "Explainability", group: "Validation", icon: "explain" },
  { to: "/experiments", label: "Experiments", group: "Validation", icon: "overview" },
  { to: "/status", label: "System Status", group: "System", icon: "status" },
];
/* Deep link (not in the menu): /overview (artifact list). */

/** Application bar: page title, snapshot / experiment selectors, channel search and live status (from /status). */
function TopBar() {
  const { status } = useResearch();
  const { pathname } = useLocation();
  const title = NAV.find((n) => n.to === pathname)?.label ?? "Research overview";
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
        <Suspense fallback={<Loading variant="block" label="Loading page…" />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/bridges" element={<BridgesPage />} />
          <Route path="/channels" element={<ChannelExplorerPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/explainability" element={<ExplainabilityPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/neural" element={<NeuralPage />} />
          <Route path="/topics" element={<TopicsPage />} />
          <Route path="/experiments" element={<ExperimentsPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </AppShell>
    </ResearchProvider>
  );
}
