import React, { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { Icon } from "../common/Icon";
import { useResearch } from "../../features/component_3/ResearchContext";
import { ExecutiveGrowthBriefModal } from "../../features/portal/ExecutiveGrowthBriefModal";

export interface DashboardNavItem {
  to: string;
  label: string;
  icon?: string;
  badge?: string;
}

interface ComponentDashboardShellProps {
  componentId: 1 | 2 | 3 | 4;
  title: string;
  subtitle: string;
  leadStudent: string;
  accentColor: string;
  nav: DashboardNavItem[];
  children: React.ReactNode;
}

export const ComponentDashboardShell: React.FC<ComponentDashboardShellProps> = ({
  componentId,
  title,
  subtitle,
  leadStudent,
  accentColor,
  nav,
  children,
}) => {
  const { status } = useResearch();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [briefOpen, setBriefOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const snap = status.status === "success" && status.data.snapshots.length > 0 ? status.data.snapshots[0] : null;

  return (
    <div className="dashboard-shell">
      {/* Dedicated Component Sidebar */}
      <aside className="dashboard-sidebar">
        <div>
          {/* Component Brand Header */}
          <div style={{ padding: "20px 18px 16px", borderBottom: "1px solid #e2e8f0" }}>
            <Link to="/" style={{ textDecoration: "none", color: "inherit", display: "flex", alignItems: "center", gap: "10px", marginBottom: "14px" }}>
              <div
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  background: accentColor,
                  color: "#ffffff",
                  display: "grid",
                  placeItems: "center",
                  fontWeight: 900,
                  fontSize: "14px",
                  boxShadow: `0 2px 8px ${accentColor}40`,
                }}
              >
                C{componentId}
              </div>
              <div>
                <div style={{ fontSize: "14px", fontWeight: 800, color: "#0f172a", lineHeight: 1.2 }}>Trendora Studio</div>
                <div style={{ fontSize: "11px", color: "#64748b" }}>Pillar {componentId} Workspace</div>
              </div>
            </Link>

            <div
              style={{
                background: `${accentColor}12`,
                border: `1px solid ${accentColor}30`,
                borderRadius: "8px",
                padding: "8px 10px",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 700, color: accentColor, textTransform: "uppercase" }}>
                {title}
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                {subtitle}
              </div>
              <div style={{ fontSize: "11px", color: "#475569", marginTop: "4px" }}>
                Lead: <strong>{leadStudent}</strong>
              </div>
            </div>
          </div>

          {/* Component Dedicated Navigation */}
          <nav style={{ padding: "16px 12px" }}>
            <div style={{ fontSize: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "#94a3b8", padding: "0 8px 8px" }}>
              Workspace Modules
            </div>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "3px" }}>
              {nav.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to.endsWith("/overview")}
                    style={({ isActive }) => ({
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "9px 12px",
                      borderRadius: "8px",
                      textDecoration: "none",
                      fontSize: "13px",
                      fontWeight: isActive ? 700 : 500,
                      background: isActive ? `${accentColor}15` : "transparent",
                      color: isActive ? accentColor : "#334155",
                      borderLeft: isActive ? `3px solid ${accentColor}` : "3px solid transparent",
                      transition: "all 0.15s",
                    })}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      {item.icon && <Icon name={item.icon} size={16} />}
                      <span>{item.label}</span>
                    </div>
                    {item.badge && (
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "10px",
                          background: `${accentColor}20`,
                          color: accentColor,
                        }}
                      >
                        {item.badge}
                      </span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div style={{ padding: "16px", borderTop: "1px solid #e2e8f0" }}>
          <Link
            to="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "12px",
              color: "#64748b",
              textDecoration: "none",
              fontWeight: 600,
              padding: "8px 10px",
              borderRadius: "6px",
              background: "#f1f5f9",
              transition: "background 0.15s",
            }}
          >
            <span>←</span> Back to Main Portal
          </Link>
          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "10px", textAlign: "center" }}>
            SLIIT CoEAI · J26-DS-334
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Top Header with Switcher */}
        <header className="dashboard-header">
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            {/* Component Switcher Dropdown */}
            <div style={{ position: "relative" }}>
              <button
                type="button"
                className="component-switcher-btn"
                onClick={() => setSwitcherOpen(!switcherOpen)}
              >
                <span
                  style={{
                    width: "18px",
                    height: "18px",
                    borderRadius: "4px",
                    background: accentColor,
                    color: "#ffffff",
                    display: "grid",
                    placeItems: "center",
                    fontSize: "10px",
                    fontWeight: 800,
                  }}
                >
                  {componentId}
                </span>
                <span>Switch Studio</span>
                <span style={{ fontSize: "10px" }}>▼</span>
              </button>

              {switcherOpen && (
                <div
                  style={{
                    position: "absolute",
                    top: "calc(100% + 8px)",
                    left: 0,
                    width: "290px",
                    background: "#ffffff",
                    border: "1px solid #cbd5e1",
                    borderRadius: "12px",
                    padding: "8px",
                    boxShadow: "0 10px 25px rgba(0, 0, 0, 0.15)",
                    zIndex: 100,
                    display: "flex",
                    flexDirection: "column",
                    gap: "4px",
                  }}
                >
                  <Link
                    to="/c1/growth-prediction"
                    onClick={() => setSwitcherOpen(false)}
                    style={{
                      display: "block",
                      padding: "8px 10px",
                      borderRadius: "6px",
                      textDecoration: "none",
                      color: "#1e293b",
                      background: componentId === 1 ? "#eff6ff" : "transparent",
                    }}
                  >
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#2563eb" }}>Pillar 1: Growth Prediction</div>
                    <div style={{ fontSize: "11px", color: "#64748b" }}>Samarasinghe S I (IT23333802)</div>
                  </Link>

                  <Link
                    to="/c2/demand-mining"
                    onClick={() => setSwitcherOpen(false)}
                    style={{
                      display: "block",
                      padding: "8px 10px",
                      borderRadius: "6px",
                      textDecoration: "none",
                      color: "#1e293b",
                      background: componentId === 2 ? "#ecfdf5" : "transparent",
                    }}
                  >
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#059669" }}>Pillar 2: Audience Demand</div>
                    <div style={{ fontSize: "11px", color: "#64748b" }}>Kahandawa K A N N (IT23307094)</div>
                  </Link>

                  <Link
                    to="/c3/audience-bridges"
                    onClick={() => setSwitcherOpen(false)}
                    style={{
                      display: "block",
                      padding: "8px 10px",
                      borderRadius: "6px",
                      textDecoration: "none",
                      color: "#1e293b",
                      background: componentId === 3 ? "#f5f3ff" : "transparent",
                    }}
                  >
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#7c3aed" }}>Pillar 3: Audience Bridges</div>
                    <div style={{ fontSize: "11px", color: "#64748b" }}>Koonara K M K C (IT23200760)</div>
                  </Link>

                  <Link
                    to="/c4/emerging-topics"
                    onClick={() => setSwitcherOpen(false)}
                    style={{
                      display: "block",
                      padding: "8px 10px",
                      borderRadius: "6px",
                      textDecoration: "none",
                      color: "#1e293b",
                      background: componentId === 4 ? "#fdf2f8" : "transparent",
                    }}
                  >
                    <div style={{ fontSize: "12px", fontWeight: 700, color: "#db2777" }}>Pillar 4: Topic Dynamics ★</div>
                    <div style={{ fontSize: "11px", color: "#64748b" }}>Sankalpa H D T P (IT23323452)</div>
                  </Link>

                  <div style={{ borderTop: "1px solid #e2e8f0", marginTop: "4px", paddingTop: "4px" }}>
                    <Link
                      to="/"
                      onClick={() => setSwitcherOpen(false)}
                      style={{
                        display: "block",
                        padding: "6px 10px",
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#64748b",
                        textDecoration: "none",
                      }}
                    >
                      ← Back to Main Home Portal
                    </Link>
                  </div>
                </div>
              )}
            </div>

            <div style={{ fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>
              {title}
            </div>
          </div>

          {/* Right Header Status & Actions */}
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            {/* 1-Click Executive Growth Brief Export Button */}
            <button
              type="button"
              onClick={() => setBriefOpen(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 12px",
                borderRadius: "8px",
                border: "1px solid #cbd5e1",
                background: "#ffffff",
                color: "#1e293b",
                fontSize: "12px",
                fontWeight: 700,
                cursor: "pointer",
                boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
              }}
            >
              <span>📑</span>
              <span>Export Brief</span>
            </button>

            {/* Interactive Changepoint Notification Bell */}
            <div style={{ position: "relative" }}>
              <button
                type="button"
                onClick={() => setAlertsOpen(!alertsOpen)}
                style={{
                  position: "relative",
                  width: "34px",
                  height: "34px",
                  borderRadius: "8px",
                  border: "1px solid #cbd5e1",
                  background: "#ffffff",
                  display: "grid",
                  placeItems: "center",
                  cursor: "pointer",
                  fontSize: "16px",
                }}
              >
                <span>🔔</span>
                <span
                  style={{
                    position: "absolute",
                    top: "-4px",
                    right: "-4px",
                    background: "#ef4444",
                    color: "#ffffff",
                    fontSize: "10px",
                    fontWeight: 800,
                    width: "16px",
                    height: "16px",
                    borderRadius: "50%",
                    display: "grid",
                    placeItems: "center",
                    boxShadow: "0 0 6px rgba(239, 68, 68, 0.6)",
                  }}
                >
                  3
                </span>
              </button>

              {/* Notification Dropdown */}
              {alertsOpen && (
                <div
                  style={{
                    position: "absolute",
                    top: "calc(100% + 8px)",
                    right: 0,
                    width: "340px",
                    background: "#ffffff",
                    border: "1px solid #cbd5e1",
                    borderRadius: "14px",
                    padding: "14px",
                    boxShadow: "0 15px 35px rgba(0, 0, 0, 0.15)",
                    zIndex: 200,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", borderBottom: "1px solid #f1f5f9", paddingBottom: "8px" }}>
                    <div style={{ fontSize: "12px", fontWeight: 800, color: "#0f172a" }}>
                      ⚡ Active BOCPD Changepoint Alerts
                    </div>
                    <span style={{ fontSize: "10px", fontWeight: 700, padding: "2px 6px", borderRadius: "10px", background: "#fce7f3", color: "#be185d" }}>
                      3 Signals
                    </span>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    <Link
                      to="/c4/cannibalization"
                      onClick={() => setAlertsOpen(false)}
                      style={{
                        display: "block",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        background: "#fdf2f8",
                        borderLeft: "3px solid #ec4899",
                        textDecoration: "none",
                        color: "inherit",
                      }}
                    >
                      <div style={{ fontSize: "12px", fontWeight: 700, color: "#9d174d" }}>
                        Acoustic Neo-Folk &amp; Unplugged
                      </div>
                      <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>
                        BOCPD Changepoint Confirmed (t=14) &middot; <strong>eTunes</strong> allocated
                      </div>
                    </Link>

                    <Link
                      to="/c4/cannibalization"
                      onClick={() => setAlertsOpen(false)}
                      style={{
                        display: "block",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        background: "#eff6ff",
                        borderLeft: "3px solid #3b82f6",
                        textDecoration: "none",
                        color: "inherit",
                      }}
                    >
                      <div style={{ fontSize: "12px", fontWeight: 700, color: "#1d4ed8" }}>
                        Teledrama Plot Deep-Dives
                      </div>
                      <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>
                        BOCPD Changepoint Confirmed (t=18) &middot; <strong>Lokaya Saha Lokayo</strong>
                      </div>
                    </Link>

                    <Link
                      to="/c4/cannibalization"
                      onClick={() => setAlertsOpen(false)}
                      style={{
                        display: "block",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        background: "#f0fdf4",
                        borderLeft: "3px solid #10b981",
                        textDecoration: "none",
                        color: "inherit",
                      }}
                    >
                      <div style={{ fontSize: "12px", fontWeight: 700, color: "#15803d" }}>
                        Investigative Historical Mysteries
                      </div>
                      <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>
                        BOCPD Changepoint Detected (t=11) &middot; <strong>DAM DERANA</strong>
                      </div>
                    </Link>
                  </div>
                </div>
              )}
            </div>

            <div style={{ width: "1px", height: "20px", background: "#e2e8f0" }} />

            <span style={{ fontSize: "12px", color: "#64748b" }}>
              Snapshot: <strong style={{ color: "#0f172a" }}>{snap?.snapshot_id || "rs-20261018T210855Z"}</strong>
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span className="pulse-dot" style={{ width: "8px", height: "8px" }} />
              <span style={{ fontSize: "12px", fontWeight: 600, color: "#16a34a" }}>Live Research DB</span>
            </div>
          </div>
        </header>

        {/* Dashboard Content */}
        <main style={{ flex: 1, padding: "24px 28px", overflowY: "auto" }}>
          {children}
        </main>
      </div>

      {/* Executive Growth Brief Modal */}
      <ExecutiveGrowthBriefModal isOpen={briefOpen} onClose={() => setBriefOpen(false)} />
    </div>
  );
};
