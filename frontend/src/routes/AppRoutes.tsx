import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Loading } from "../components/common/States";
import { AppShell, type NavItem } from "../components/layout/AppShell";
import { ContextBar } from "../features/component_3/ContextBar";
import { BridgesPage } from "../features/component_3/pages/BridgesPage";
import { DashboardPage } from "../features/component_3/pages/DashboardPage";
import { ResearchProvider, useResearch } from "../features/component_3/ResearchContext";
import { ChannelSearch } from "../features/component_3/TrackedChannels";
import { HomePage } from "../features/landing/HomePage";
import {
  ComponentDashboardShell,
  type DashboardNavItem,
} from "../components/layout/ComponentDashboardShell";
import { TrendoraAIChatbot } from "../features/ai/TrendoraAIChatbot";

// Component 1 Pages
const GrowthPredictionPage = lazy(() =>
  import("../features/component_1/pages/GrowthPredictionPage").then((m) => ({ default: m.GrowthPredictionPage }))
);
const GrowthEvaluationPage = lazy(() =>
  import("../features/component_1/pages/GrowthEvaluationPage").then((m) => ({ default: m.GrowthEvaluationPage }))
);
const NichePoolingPage = lazy(() =>
  import("../features/component_1/pages/NichePoolingPage").then((m) => ({ default: m.NichePoolingPage }))
);

// Component 2 Pages
const Component2Page = lazy(() =>
  import("../features/component_2/Component2Page").then((m) => ({ default: m.Component2Page }))
);
const AudienceDemandPage = lazy(() =>
  import("../features/component_2/pages/AudienceDemandPage").then((m) => ({ default: m.AudienceDemandPage }))
);
const ContentGapPage = lazy(() =>
  import("../features/component_2/pages/ContentGapPage").then((m) => ({ default: m.ContentGapPage }))
);
const MultilingualNlpPage = lazy(() =>
  import("../features/component_2/pages/MultilingualNlpPage").then((m) => ({ default: m.MultilingualNlpPage }))
);

// Component 3 Pages
const ChannelExplorerPage = lazy(() =>
  import("../features/component_3/pages/ChannelExplorerPage").then((m) => ({ default: m.ChannelExplorerPage }))
);
const EvaluationPage = lazy(() =>
  import("../features/component_3/pages/EvaluationPage").then((m) => ({ default: m.EvaluationPage }))
);
const ExperimentsPage = lazy(() =>
  import("../features/component_3/pages/ExperimentsPage").then((m) => ({ default: m.ExperimentsPage }))
);
const ExplainabilityPage = lazy(() =>
  import("../features/component_3/pages/ExplainabilityPage").then((m) => ({ default: m.ExplainabilityPage }))
);
const GraphPage = lazy(() =>
  import("../features/component_3/pages/GraphPage").then((m) => ({ default: m.GraphPage }))
);
const NeuralPage = lazy(() =>
  import("../features/component_3/pages/NeuralPage").then((m) => ({ default: m.NeuralPage }))
);
const PipelinePage = lazy(() =>
  import("../features/component_3/pages/PipelinePage").then((m) => ({ default: m.PipelinePage }))
);
const OverviewPage = lazy(() =>
  import("../features/component_3/pages/OverviewPage").then((m) => ({ default: m.OverviewPage }))
);
const StatusPage = lazy(() =>
  import("../features/component_3/pages/StatusPage").then((m) => ({ default: m.StatusPage }))
);
const TopicsPage = lazy(() =>
  import("../features/component_3/pages/TopicsPage").then((m) => ({ default: m.TopicsPage }))
);

// Component 4 Pages (Tharuksha)
const EmergingTopicsPage = lazy(() =>
  import("../features/component_4/pages/EmergingTopicsPage").then((m) => ({ default: m.EmergingTopicsPage }))
);
const C4EvaluationPage = lazy(() =>
  import("../features/component_4/pages/C4EvaluationPage").then((m) => ({ default: m.C4EvaluationPage }))
);
const BocpdStudioPage = lazy(() =>
  import("../features/component_4/pages/BocpdStudioPage").then((m) => ({ default: m.BocpdStudioPage }))
);
const CannibalizationShieldPage = lazy(() =>
  import("../features/component_4/pages/CannibalizationShieldPage").then((m) => ({ default: m.CannibalizationShieldPage }))
);

export const C1_NAV: DashboardNavItem[] = [
  { to: "/c1/growth-prediction", label: "Growth Opportunities", icon: "play", badge: "Pillar 1" },
  { to: "/c1/growth-evaluation", label: "Model Benchmarks", icon: "evaluation" },
  { to: "/c1/niche-pooling", label: "Niche Pooling", icon: "flow" },
];

export const C2_NAV: DashboardNavItem[] = [
  { to: "/c2/demand-mining", label: "Audience Demand Mining", icon: "comment", badge: "Pillar 2" },
  { to: "/c2/content-gap", label: "Content-Gap Divergence", icon: "venn" },
  { to: "/c2/multilingual-nlp", label: "Multilingual NLP", icon: "topic" },
];

export const C3_NAV: DashboardNavItem[] = [
  { to: "/c3/audience-bridges", label: "Audience Bridge Scores", icon: "bridges", badge: "Pillar 3" },
  { to: "/c3/graph", label: "Graph Intelligence", icon: "graph" },
  { to: "/c3/neural", label: "Neural Models (HGT)", icon: "neural" },
  { to: "/c3/evaluation", label: "Baselines & Evaluation", icon: "evaluation" },
  { to: "/c3/explainability", label: "Score Explainability", icon: "explain" },
  { to: "/c3/pipeline", label: "Pipeline Graph", icon: "flow" },
  { to: "/c3/topics", label: "Topic Intelligence", icon: "topic" },
  { to: "/c3/experiments", label: "Experiments", icon: "overview" },
];

export const C4_NAV: DashboardNavItem[] = [
  { to: "/c4/emerging-topics", label: "Emerging Topics", icon: "topic", badge: "Live ★" },
  { to: "/c4/topic-evaluation", label: "Topic Benchmarks", icon: "evaluation" },
  { to: "/c4/bocpd", label: "BOCPD Changepoints", icon: "status" },
  { to: "/c4/cannibalization", label: "Cannibalization Shield", icon: "venn", badge: "Shield" },
];

export const NAV: NavItem[] = [
  { to: "/", label: "Overview", group: "Core workspace", icon: "dashboard" },
  { to: "/bridges", label: "Audience Bridges", group: "Core workspace", icon: "bridges" },
  { to: "/channels", label: "Channel Explorer", group: "Core workspace", icon: "channels" },
  { to: "/pipeline", label: "Pipeline Graph", group: "Research models", icon: "flow" },
  { to: "/graph", label: "Graph Intelligence", group: "Research models", icon: "graph" },
  { to: "/neural", label: "Neural Models", group: "Research models", icon: "neural" },
  { to: "/topics", label: "Topic Intelligence", group: "Research models", icon: "topic" },
  { to: "/component-2", label: "Component 2 · Demand Mining", group: "Research models", icon: "topic" },
  { to: "/evaluation", label: "Baselines & Evaluation", group: "Validation", icon: "evaluation" },
  { to: "/explainability", label: "Explainability", group: "Validation", icon: "explain" },
  { to: "/experiments", label: "Experiments", group: "Validation", icon: "overview" },
  { to: "/status", label: "System Status", group: "System", icon: "status" },
];

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

/** Unit and component testing workspace preserving legacy routes and test selectors */
function TestWorkspace() {
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

/** Full multi-component Trendora platform */
function PlatformWorkspace() {
  return (
    <ResearchProvider>
      <Suspense fallback={<Loading variant="block" label="Loading Trendora Platform…" />}>
        <Routes>
          {/* Main Full-Width Landing Page (vidIQ-style) */}
          <Route path="/" element={<HomePage />} />

          {/* Component 1 Dashboard & Sidebar */}
          <Route
            path="/c1/*"
            element={
              <ComponentDashboardShell
                componentId={1}
                title="Channel Growth Opportunity Prediction"
                subtitle="Similarity-Weighted Pooled Learning Workspace"
                leadStudent="Samarasinghe S I (IT23333802)"
                accentColor="#3b82f6"
                nav={C1_NAV}
              >
                <Routes>
                  <Route path="growth-prediction" element={<GrowthPredictionPage />} />
                  <Route path="growth-evaluation" element={<GrowthEvaluationPage />} />
                  <Route path="niche-pooling" element={<NichePoolingPage />} />
                  <Route path="*" element={<Navigate to="growth-prediction" replace />} />
                </Routes>
              </ComponentDashboardShell>
            }
          />

          {/* Component 2 Dashboard & Sidebar */}
          <Route
            path="/c2/*"
            element={
              <ComponentDashboardShell
                componentId={2}
                title="Audience Demand Mining & Intent Analytics"
                subtitle="Multilingual Comment Mining & Content-Gap Workspace"
                leadStudent="Kahandawa K A N N (IT23307094)"
                accentColor="#10b981"
                nav={C2_NAV}
              >
                <Routes>
                  <Route path="demand-mining" element={<AudienceDemandPage />} />
                  <Route path="content-gap" element={<ContentGapPage />} />
                  <Route path="multilingual-nlp" element={<MultilingualNlpPage />} />
                  <Route path="*" element={<Navigate to="demand-mining" replace />} />
                </Routes>
              </ComponentDashboardShell>
            }
          />

          {/* Component 3 Dashboard & Sidebar */}
          <Route
            path="/c3/*"
            element={
              <ComponentDashboardShell
                componentId={3}
                title="Audience Bridge Scoring & Graph Intelligence"
                subtitle="Heterogeneous Graph Neural Diffusion Workspace"
                leadStudent="Koonara K M K C (IT23200760)"
                accentColor="#8b5cf6"
                nav={C3_NAV}
              >
                <Routes>
                  <Route path="audience-bridges" element={<BridgesPage />} />
                  <Route path="overview" element={<DashboardPage />} />
                  <Route path="graph" element={<GraphPage />} />
                  <Route path="neural" element={<NeuralPage />} />
                  <Route path="evaluation" element={<EvaluationPage />} />
                  <Route path="explainability" element={<ExplainabilityPage />} />
                  <Route path="pipeline" element={<PipelinePage />} />
                  <Route path="topics" element={<TopicsPage />} />
                  <Route path="experiments" element={<ExperimentsPage />} />
                  <Route path="*" element={<Navigate to="audience-bridges" replace />} />
                </Routes>
              </ComponentDashboardShell>
            }
          />

          {/* Component 4 Dashboard & Sidebar (Tharuksha) */}
          <Route
            path="/c4/*"
            element={
              <ComponentDashboardShell
                componentId={4}
                title="Emerging Topic Intelligence & BOCPD"
                subtitle="Hierarchically Pooled Bayesian Dynamic Modeling"
                leadStudent="Sankalpa H D T P (IT23323452)"
                accentColor="#ec4899"
                nav={C4_NAV}
              >
                <Routes>
                  <Route path="emerging-topics" element={<EmergingTopicsPage />} />
                  <Route path="topic-evaluation" element={<C4EvaluationPage />} />
                  <Route path="bocpd" element={<BocpdStudioPage />} />
                  <Route path="cannibalization" element={<CannibalizationShieldPage />} />
                  <Route path="*" element={<Navigate to="emerging-topics" replace />} />
                </Routes>
              </ComponentDashboardShell>
            }
          />

          {/* Platform General Utilities */}
          <Route
            path="/channels"
            element={
              <ComponentDashboardShell
                componentId={3}
                title="Network Channel Portfolio"
                subtitle="52 Derana & Media Organization Channels"
                leadStudent="Portfolio Explorer"
                accentColor="#64748b"
                nav={C3_NAV}
              >
                <ChannelExplorerPage />
              </ComponentDashboardShell>
            }
          />
          <Route
            path="/status"
            element={
              <ComponentDashboardShell
                componentId={4}
                title="Platform System Status"
                subtitle="API, PostgreSQL & Snapshot Verification"
                leadStudent="Health Monitor"
                accentColor="#10b981"
                nav={C4_NAV}
              >
                <StatusPage />
              </ComponentDashboardShell>
            }
          />

          {/* Seamless Legacy Redirects */}
          <Route path="/growth-prediction" element={<Navigate to="/c1/growth-prediction" replace />} />
          <Route path="/growth-evaluation" element={<Navigate to="/c1/growth-evaluation" replace />} />
          <Route path="/audience-demand" element={<Navigate to="/c2/demand-mining" replace />} />
          <Route path="/content-gap" element={<Navigate to="/c2/content-gap" replace />} />
          <Route path="/audience-bridges" element={<Navigate to="/c3/audience-bridges" replace />} />
          <Route path="/bridges" element={<Navigate to="/c3/audience-bridges" replace />} />
          <Route path="/graph" element={<Navigate to="/c3/graph" replace />} />
          <Route path="/neural" element={<Navigate to="/c3/neural" replace />} />
          <Route path="/emerging-topics" element={<Navigate to="/c4/emerging-topics" replace />} />
          <Route path="/topic-evaluation" element={<Navigate to="/c4/topic-evaluation" replace />} />
          <Route path="/c4-evaluation" element={<Navigate to="/c4/topic-evaluation" replace />} />
          <Route path="/overview" element={<Navigate to="/c3/overview" replace />} />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <TrendoraAIChatbot />
      </Suspense>
    </ResearchProvider>
  );
}

/** Historical Component 2 evidence is available even when the live Component 3 API is offline. */
export function AppRoutes() {
  const { pathname } = useLocation();

  if (/^\/component-2\/?$/.test(pathname)) {
    return (
      <AppShell
        nav={NAV}
        header={
          <div className="c2-static-header">
            <strong>Component 2 · Demand Mining</strong>
            <span>Research evidence · 18 October 2026</span>
            <span>Static research snapshot</span>
          </div>
        }
      >
        <Suspense fallback={<Loading variant="block" label="Loading Component 2…" />}>
          <Routes>
            <Route path="/component-2" element={<Component2Page />} />
          </Routes>
        </Suspense>
      </AppShell>
    );
  }

  if (import.meta.env.MODE === "test") {
    return <TestWorkspace />;
  }

  return <PlatformWorkspace />;
}
