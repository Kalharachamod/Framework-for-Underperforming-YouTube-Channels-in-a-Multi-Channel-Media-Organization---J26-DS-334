import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell, type NavItem } from "../components/layout/AppShell";
import { ContextBar } from "../features/component_3/ContextBar";
import { BridgesPage } from "../features/component_3/pages/BridgesPage";
import { ChannelExplorerPage } from "../features/component_3/pages/ChannelExplorerPage";
import { EvaluationPage } from "../features/component_3/pages/EvaluationPage";
import { ExplainabilityPage } from "../features/component_3/pages/ExplainabilityPage";
import { OverviewPage } from "../features/component_3/pages/OverviewPage";
import { StatusPage } from "../features/component_3/pages/StatusPage";
import { ResearchProvider } from "../features/component_3/ResearchContext";

export const NAV: NavItem[] = [
  { to: "/", label: "Overview" },
  { to: "/bridges", label: "Audience Bridges" },
  { to: "/channels", label: "Channel Explorer" },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/explainability", label: "Explainability" },
  { to: "/status", label: "System Status" },
];

export function AppRoutes() {
  return (
    <ResearchProvider>
      <AppShell nav={NAV} header={<ContextBar />}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
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
