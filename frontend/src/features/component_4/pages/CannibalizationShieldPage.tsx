import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface AllocationItem {
  channel_name: string;
  channel_tier: string;
  role: string;
  role_badge: string;
  fit_score: number;
  directive: string;
}

interface CannibalizationTopic {
  topic_id: number;
  topic_name: string;
  niche: string;
  network_risk: string;
  risk_color: string;
  bocpd_status: string;
  estimated_views_protected: number;
  allocations: AllocationItem[];
}

export const CannibalizationShieldPage: React.FC = () => {
  const [topics, setTopics] = useState<CannibalizationTopic[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedTopicId, setSelectedTopicId] = useState<number>(4);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/v1/component-4/cannibalization-shield")
      .then((res) => res.json())
      .then((data) => {
        setTopics(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const activeTopic = topics.find((t) => t.topic_id === selectedTopicId) || topics[0];
  const totalViewsProtected = topics.reduce((acc, t) => acc + t.estimated_views_protected, 0);

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div
          style={{
            display: "inline-block",
            padding: "4px 10px",
            background: "#fee2e2",
            color: "#b91c1c",
            borderRadius: "16px",
            fontSize: "12px",
            fontWeight: 700,
            marginBottom: "8px",
          }}
        >
          RESEARCH PILLAR 4 · MULTI-CHANNEL ALLOCATION ENGINE
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Multi-Channel Cannibalization Shield &amp; Production Allocation
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Preventing self-competition across 52 network channels by allocating exclusive first-mover production to underperforming channels
        </p>
      </div>

      {/* KPI Stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #10b981" }}>
          <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Protected Network Views
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0", color: "#16a34a" }}>
            +{totalViewsProtected.toLocaleString()} Views
          </div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Saved from internal sister-channel overlap</div>
        </div>

        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #ec4899" }}>
          <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Target Channels Empowered
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0", color: "#ec4899" }}>
            eTunes · Lokaya · DAM
          </div>
          <div style={{ fontSize: "12px", color: "#16a34a", fontWeight: 600 }}>Exclusive production windows granted</div>
        </div>

        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #3b82f6" }}>
          <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Flagship Coordination
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>TV Derana &amp; Ada Derana</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Repurposed as Bridge Promoters</div>
        </div>

        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #8b5cf6" }}>
          <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Allocation Formula
          </div>
          <div style={{ fontSize: "18px", fontWeight: 800, margin: "4px 0" }}>Fit &times; (1 - Overlap)</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Dynamic Channel Fit Scoring</div>
        </div>
      </div>

      {/* Main Analysis Card */}
      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>
              Active Emerging Topics &amp; Network Defense Plans {loading && <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 500 }}>(Refreshing...)</span>}
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--muted)" }}>
              Select an emerging topic detected by BOCPD to view the network production allocation plan.
            </p>
          </div>

          {/* Topic Selector Tabs */}
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {topics.map((t) => (
              <button
                key={t.topic_id}
                onClick={() => setSelectedTopicId(t.topic_id)}
                style={{
                  padding: "8px 14px",
                  borderRadius: "8px",
                  border: selectedTopicId === t.topic_id ? "2px solid #ec4899" : "1px solid #cbd5e1",
                  background: selectedTopicId === t.topic_id ? "#fdf2f8" : "#ffffff",
                  color: selectedTopicId === t.topic_id ? "#be185d" : "#475569",
                  fontWeight: 700,
                  fontSize: "12px",
                  cursor: "pointer",
                }}
              >
                Topic #{t.topic_id}: {t.niche}
              </button>
            ))}
          </div>
        </div>

        {activeTopic && (
          <div>
            {/* Active Topic Banner */}
            <div
              style={{
                background: "#f8fafc",
                borderRadius: "12px",
                padding: "16px 20px",
                marginBottom: "20px",
                border: "1px solid #e2e8f0",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "12px",
              }}
            >
              <div>
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 800,
                    padding: "3px 8px",
                    borderRadius: "6px",
                    background: `${activeTopic.risk_color}18`,
                    color: activeTopic.risk_color,
                    textTransform: "uppercase",
                  }}
                >
                  Cannibalization Risk: {activeTopic.network_risk}
                </span>
                <h2 style={{ margin: "6px 0 2px", fontSize: "20px", fontWeight: 800, color: "#0f172a" }}>
                  {activeTopic.topic_name}
                </h2>
                <div style={{ fontSize: "12px", color: "#64748b" }}>
                  BOCPD Status: <strong>{activeTopic.bocpd_status}</strong>
                </div>
              </div>

              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase", fontWeight: 700 }}>
                  Incremental Views Saved
                </div>
                <div style={{ fontSize: "22px", fontWeight: 800, color: "#16a34a" }}>
                  +{activeTopic.estimated_views_protected.toLocaleString()}
                </div>
              </div>
            </div>

            {/* Allocation Roles Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
              {activeTopic.allocations.map((alloc) => {
                const isPrimary = alloc.role_badge.includes("PRIMARY");
                const isBridge = alloc.role_badge.includes("BRIDGE");
                const borderColor = isPrimary ? "#10b981" : isBridge ? "#3b82f6" : "#f59e0b";

                return (
                  <div
                    key={alloc.channel_name}
                    style={{
                      background: "#ffffff",
                      borderRadius: "12px",
                      padding: "18px",
                      border: `1px solid #e2e8f0`,
                      borderTop: `4px solid ${borderColor}`,
                      boxShadow: "0 2px 4px rgba(0,0,0,0.03)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                      <div>
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 800,
                            padding: "3px 8px",
                            borderRadius: "12px",
                            background: `${borderColor}20`,
                            color: borderColor,
                            letterSpacing: "0.5px",
                          }}
                        >
                          {alloc.role_badge}
                        </span>
                        <h4 style={{ margin: "8px 0 2px", fontSize: "16px", fontWeight: 800, color: "#0f172a" }}>
                          {alloc.channel_name}
                        </h4>
                        <div style={{ fontSize: "11px", color: "#64748b" }}>{alloc.channel_tier}</div>
                      </div>

                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "10px", color: "#64748b" }}>Channel Fit</div>
                        <div style={{ fontSize: "16px", fontWeight: 800, color: borderColor }}>
                          {Math.round(alloc.fit_score * 100)}%
                        </div>
                      </div>
                    </div>

                    <div style={{ marginTop: "12px", background: "#f8fafc", padding: "10px 12px", borderRadius: "8px", fontSize: "12px", color: "#334155", lineHeight: "1.5" }}>
                      <strong>Operational Directive:</strong> {alloc.directive}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Academic Problem Statement Formulation */}
      <div className="card" style={{ padding: "24px" }}>
        <h3 style={{ margin: "0 0 12px 0", fontSize: "17px", fontWeight: 700 }}>
          🔬 The Multi-Channel Cannibalization Problem in Media Networks
        </h3>
        <p style={{ margin: "0 0 12px 0", fontSize: "14px", color: "#334155", lineHeight: "1.7" }}>
          In a large organization like the <strong>Derana Media Network (52 channels)</strong>, high-velocity topics naturally attract multiple production units. If the network allows its flagship (e.g. TV Derana) to immediately produce coverage on a topic when it first emerges, the flagship’s immense subscriber base completely drowns out younger or underperforming channels (e.g. eTunes, Lokaya Saha Lokayo).
        </p>
        <ul style={{ margin: "0 0 16px 0", paddingLeft: "20px", fontSize: "13px", lineHeight: "1.8", color: "#475569" }}>
          <li>
            <strong>First-Mover Exclusive Windows:</strong> Component 4 awards exclusive 14-day production windows to the highest-fit underperforming channel, allowing them to capture the high initial view velocity $v_{24}$.
          </li>
          <li>
            <strong>Flagship Bridge Routing:</strong> Rather than producing duplicate competing video files, network flagships deploy community posts and end-screens directing audiences into the underperforming channel.
          </li>
          <li>
            <strong>Network Portfolio Maximization:</strong> Preserves total network viewership while lifting lagging channels out of underperformance.
          </li>
        </ul>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Link to="/c4/bocpd" className="button" style={{ textDecoration: "none" }}>
            ← Back to BOCPD Hyperparameter Studio
          </Link>
          <Link to="/c4/emerging-topics" className="button" style={{ textDecoration: "none" }}>
            Emerging Topics Feed →
          </Link>
        </div>
      </div>
    </div>
  );
};
