import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell, type NavItem } from "../components/layout/AppShell";
import { ContextBar } from "../features/component_3/ContextBar";
import { BridgesPage } from "../features/component_3/pages/BridgesPage";
import { ChannelExplorerPage } from "../features/component_3/pages/ChannelExplorerPage";
import { DashboardPage } from "../features/component_3/pages/DashboardPage";
import { EvaluationPage } from "../features/component_3/pages/EvaluationPage";
import { ExplainabilityPage } from "../features/component_3/pages/ExplainabilityPage";
import { OverviewPage } from "../features/component_3/pages/OverviewPage";
import { StatusPage } from "../features/component_3/pages/StatusPage";
import { ResearchProvider } from "../features/component_3/ResearchContext";
import { ChannelSearch, TrackedChannels } from "../features/component_3/TrackedChannels";

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", group: "Insights", icon: "dashboard" },
  { to: "/bridges", label: "Audience Bridges", group: "Insights", icon: "bridges" },
  { to: "/channels", label: "Channel Explorer", group: "Insights", icon: "channels" },
  { to: "/explainability", label: "Explainability", group: "Insights", icon: "explain" },
  { to: "/evaluation", label: "Evaluation", group: "Research", icon: "evaluation" },
  { to: "/overview", label: "Research Overview", group: "Research", icon: "overview" },
  { to: "/status", label: "System Status", group: "System", icon: "status" },
];

export function AppRoutes() {
  return (
    <ResearchProvider>
      <AppShell nav={NAV} sidebarExtra={<TrackedChannels />}
        header={<div className="topbar__row"><ChannelSearch /><ContextBar /></div>}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/bridges" element={<BridgesPage />} />
          <Route path="/channels" element={<ChannelExplorerPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/explainability" element={<ExplainabilityPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </ResearchProvider>
  );
}
