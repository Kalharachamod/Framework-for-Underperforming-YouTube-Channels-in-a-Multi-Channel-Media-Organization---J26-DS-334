import React from "react";
import { Link } from "react-router-dom";
import { useResearch } from "../component_3/ResearchContext";
import { Icon } from "../../components/common/Icon";

export const ExecutivePortalPage: React.FC = () => {
  const { status } = useResearch();
  const snap = status.status === "success" && status.data.snapshots.length > 0 ? status.data.snapshots[0] : null;

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "24px 20px" }}>
      {/* Hero Section */}
      <div
        style={{
          background: "linear-gradient(135deg, #1e3a8a 0%, #1e1b4b 60%, #0f172a 100%)",
          borderRadius: "18px",
          padding: "36px 32px",
          color: "#ffffff",
          boxShadow: "0 10px 25px -5px rgba(15, 23, 42, 0.3)",
          marginBottom: "28px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "12px", flexWrap: "wrap" }}>
          <span
            style={{
              background: "rgba(59, 130, 246, 0.3)",
              color: "#93c5fd",
              border: "1px solid rgba(147, 197, 253, 0.3)",
              padding: "4px 12px",
              borderRadius: "20px",
              fontSize: "12px",
              fontWeight: 700,
              letterSpacing: "0.5px",
            }}
          >
            SLIIT CoEAI RESEARCH · J26-DS-334
          </span>
          <span
            style={{
              background: "rgba(16, 185, 129, 0.25)",
              color: "#6ee7b7",
              border: "1px solid rgba(110, 231, 183, 0.3)",
              padding: "4px 12px",
              borderRadius: "20px",
              fontSize: "12px",
              fontWeight: 600,
            }}
          >
            Derana Media Network Portfolio (52 Channels)
          </span>
          <span
            style={{
              background: "rgba(255, 255, 255, 0.1)",
              color: "#e2e8f0",
              padding: "4px 12px",
              borderRadius: "20px",
              fontSize: "12px",
            }}
          >
            Active Snapshot: {snap?.snapshot_id || "rs-20261018T210855Z"}
          </span>
        </div>

        <h1 style={{ fontSize: "32px", fontWeight: 800, margin: "8px 0 12px 0", letterSpacing: "-0.5px", color: "#ffffff" }}>
          Trendora: Growth Intelligence Platform
        </h1>
        <p style={{ fontSize: "16px", color: "#cbd5e1", maxWidth: "860px", lineHeight: "1.6", margin: 0 }}>
          An end-to-end data science framework designed to identify, analyze, and revive underperforming YouTube channels within a multi-channel media organization through pooled machine learning, audience demand mining, graph neural diffusion, and Bayesian dynamic topic modeling.
        </p>

        {/* Quick jump pills */}
        <div style={{ display: "flex", gap: "10px", marginTop: "24px", flexWrap: "wrap" }}>
          <Link
            to="/growth-prediction"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(255, 255, 255, 0.12)",
              color: "#ffffff",
              padding: "8px 14px",
              borderRadius: "8px",
              textDecoration: "none",
              fontSize: "13px",
              fontWeight: 600,
              border: "1px solid rgba(255, 255, 255, 0.18)",
              transition: "background 0.2s",
            }}
          >
            <span style={{ color: "#60a5fa" }}>●</span> Pillar 1: Growth Prediction
          </Link>
          <Link
            to="/audience-demand"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(255, 255, 255, 0.12)",
              color: "#ffffff",
              padding: "8px 14px",
              borderRadius: "8px",
              textDecoration: "none",
              fontSize: "13px",
              fontWeight: 600,
              border: "1px solid rgba(255, 255, 255, 0.18)",
              transition: "background 0.2s",
            }}
          >
            <span style={{ color: "#34d399" }}>●</span> Pillar 2: Audience Demand
          </Link>
          <Link
            to="/audience-bridges"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(255, 255, 255, 0.12)",
              color: "#ffffff",
              padding: "8px 14px",
              borderRadius: "8px",
              textDecoration: "none",
              fontSize: "13px",
              fontWeight: 600,
              border: "1px solid rgba(255, 255, 255, 0.18)",
              transition: "background 0.2s",
            }}
          >
            <span style={{ color: "#a78bfa" }}>●</span> Pillar 3: Audience Bridges
          </Link>
          <Link
            to="/emerging-topics"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(255, 255, 255, 0.2)",
              color: "#ffffff",
              padding: "8px 14px",
              borderRadius: "8px",
              textDecoration: "none",
              fontSize: "13px",
              fontWeight: 700,
              border: "1px solid #60a5fa",
              boxShadow: "0 0 12px rgba(59, 130, 246, 0.4)",
            }}
          >
            <span style={{ color: "#f472b6" }}>★</span> Pillar 4: Emerging Topics (Live)
          </Link>
        </div>
      </div>

      {/* Portfolio Quick Stats Bar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "32px" }}>
        <div className="card" style={{ padding: "18px 20px", borderLeft: "4px solid #3b82f6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>
            Network Channels
          </div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text)", margin: "4px 0" }}>
            52 Channels
          </div>
          <div style={{ fontSize: "13px", color: "#16a34a", fontWeight: 600 }}>
            31,986,355 Combined Subscribers
          </div>
        </div>

        <div className="card" style={{ padding: "18px 20px", borderLeft: "4px solid #10b981" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>
            Analyzed Video Repository
          </div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text)", margin: "4px 0" }}>
            1,682 Videos
          </div>
          <div style={{ fontSize: "13px", color: "var(--muted)" }}>
            Shorts & Long-form Content
          </div>
        </div>

        <div className="card" style={{ padding: "18px 20px", borderLeft: "4px solid #8b5cf6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>
            Public Audience Comments
          </div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text)", margin: "4px 0" }}>
            26,513 Comments
          </div>
          <div style={{ fontSize: "13px", color: "var(--muted)" }}>
            16,976 Pseudonymized Viewers
          </div>
        </div>

        <div className="card" style={{ padding: "18px 20px", borderLeft: "4px solid #ec4899" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>
            Emerging Topic Signals
          </div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text)", margin: "4px 0" }}>
            8 Detected Signals
          </div>
          <div style={{ fontSize: "13px", color: "#2563eb", fontWeight: 600 }}>
            20.0% False Alarm Rate (Hierarchical)
          </div>
        </div>
      </div>

      {/* 4 Research Pillars Grid */}
      <div style={{ marginBottom: "36px" }}>
        <div style={{ marginBottom: "16px" }}>
          <h2 style={{ fontSize: "22px", fontWeight: 800, margin: "0 0 4px 0" }}>
            The 4 Research Pillars
          </h2>
          <p style={{ fontSize: "14px", color: "var(--muted)" }}>
            Comprehensive breakdown of individual research contributions across the multi-channel intelligence framework.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))", gap: "20px" }}>
          {/* Pillar 1 Card */}
          <div
            className="card"
            style={{
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              borderRadius: "14px",
              borderTop: "4px solid #3b82f6",
              boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "12px", background: "#dbeafe", color: "#1d4ed8" }}>
                  PILLAR 1
                </span>
                <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 500 }}>
                  IT23333802
                </span>
              </div>
              <h3 style={{ margin: "6px 0 10px 0", fontSize: "18px", fontWeight: 700 }}>
                Channel Growth Prediction
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.6", margin: "0 0 14px 0" }}>
                Channel-specific growth opportunity prediction using pooled learning across niche-similar channels. Normalizes views/subscribers, engagement velocities, and trains XGBoost/LightGBM classifiers.
              </p>
              <div style={{ background: "var(--surface-2)", padding: "10px 12px", borderRadius: "8px", fontSize: "12px", marginBottom: "16px" }}>
                <div><strong>Lead:</strong> Samarasinghe S I</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> Pooled XGBoost, LightGBM, SHAP</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <Link
                to="/growth-prediction"
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: "9px 14px",
                  borderRadius: "8px",
                  background: "#3b82f6",
                  color: "#ffffff",
                  textDecoration: "none",
                  fontWeight: 600,
                  fontSize: "13px",
                }}
              >
                Growth Dashboard →
              </Link>
            </div>
          </div>

          {/* Pillar 2 Card */}
          <div
            className="card"
            style={{
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              borderRadius: "14px",
              borderTop: "4px solid #10b981",
              boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "12px", background: "#d1fae5", color: "#047857" }}>
                  PILLAR 2
                </span>
                <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 500 }}>
                  IT23307094
                </span>
              </div>
              <h3 style={{ margin: "6px 0 10px 0", fontSize: "18px", fontWeight: 700 }}>
                Audience Demand Mining
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.6", margin: "0 0 14px 0" }}>
                Quantifies audience demand signals from 26,500+ viewer comments using multilingual text processing (Sinhala, English, Tanglish), intent classification, and Jensen-Shannon content-gap divergence.
              </p>
              <div style={{ background: "var(--surface-2)", padding: "10px 12px", borderRadius: "8px", fontSize: "12px", marginBottom: "16px" }}>
                <div><strong>Lead:</strong> Kahandawa K A N N</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> Multilingual NLP, JS Divergence</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <Link
                to="/audience-demand"
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: "9px 14px",
                  borderRadius: "8px",
                  background: "#10b981",
                  color: "#ffffff",
                  textDecoration: "none",
                  fontWeight: 600,
                  fontSize: "13px",
                }}
              >
                Demand Explorer →
              </Link>
            </div>
          </div>

          {/* Pillar 3 Card */}
          <div
            className="card"
            style={{
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              borderRadius: "14px",
              borderTop: "4px solid #8b5cf6",
              boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "12px", background: "#ede9fe", color: "#6d28d9" }}>
                  PILLAR 3
                </span>
                <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 500 }}>
                  IT23200760
                </span>
              </div>
              <h3 style={{ margin: "6px 0 10px 0", fontSize: "18px", fontWeight: 700 }}>
                Audience Bridge Scoring
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.6", margin: "0 0 14px 0" }}>
                Diffusion-based cross-channel audience bridge scoring across 52 channels. Constructs a heterogeneous graph (Channel-Video-Commenter), trains metapath2vec & HGT embeddings, and executes Personalized PageRank.
              </p>
              <div style={{ background: "var(--surface-2)", padding: "10px 12px", borderRadius: "8px", fontSize: "12px", marginBottom: "16px" }}>
                <div><strong>Lead:</strong> Koonara K M K C</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> HGT, metapath2vec, PPR Diffusion</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <Link
                to="/audience-bridges"
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: "9px 14px",
                  borderRadius: "8px",
                  background: "#8b5cf6",
                  color: "#ffffff",
                  textDecoration: "none",
                  fontWeight: 600,
                  fontSize: "13px",
                }}
              >
                Bridge Intelligence →
              </Link>
            </div>
          </div>

          {/* Pillar 4 Card */}
          <div
            className="card"
            style={{
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              borderRadius: "14px",
              borderTop: "4px solid #ec4899",
              background: "linear-gradient(180deg, #ffffff 0%, #fdf2f8 100%)",
              boxShadow: "0 4px 12px rgba(236, 72, 153, 0.12)",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "12px", background: "#fce7f3", color: "#be185d" }}>
                  PILLAR 4 · ACTIVE
                </span>
                <span style={{ fontSize: "12px", color: "#be185d", fontWeight: 700 }}>
                  IT23323452 (Tharuksha)
                </span>
              </div>
              <h3 style={{ margin: "6px 0 10px 0", fontSize: "18px", fontWeight: 800, color: "#831843" }}>
                Dynamic Topic Intelligence
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.6", margin: "0 0 14px 0" }}>
                Hierarchically Pooled Dynamic Topic Modelling with Bayesian Online Changepoint Detection (BOCPD). Shrinks noisy estimates via Empirical Bayes to cut false trend alarms from 44.8% to 20.0% with 95% Credible Intervals.
              </p>
              <div style={{ background: "#ffffff", padding: "10px 12px", borderRadius: "8px", fontSize: "12px", marginBottom: "16px", border: "1px solid #fbcfe8" }}>
                <div><strong>Lead:</strong> Sankalpa H D T P</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> Hierarchical Bayes, BOCPD, Topic Dynamics</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <Link
                to="/emerging-topics"
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: "9px 14px",
                  borderRadius: "8px",
                  background: "#ec4899",
                  color: "#ffffff",
                  textDecoration: "none",
                  fontWeight: 700,
                  fontSize: "13px",
                  boxShadow: "0 2px 6px rgba(236, 72, 153, 0.3)",
                }}
              >
                Emerging Topics (Live) ★
              </Link>
              <Link
                to="/topic-evaluation"
                style={{
                  padding: "9px 12px",
                  borderRadius: "8px",
                  background: "#ffffff",
                  color: "#be185d",
                  textDecoration: "none",
                  fontWeight: 600,
                  fontSize: "13px",
                  border: "1px solid #fbcfe8",
                }}
              >
                Benchmarks
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Cross-Component Synergy Workflow */}
      <div className="card" style={{ padding: "28px", borderRadius: "16px", marginBottom: "32px" }}>
        <h3 style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 8px 0" }}>
          Integrated Multi-Channel Revival Workflow
        </h3>
        <p style={{ fontSize: "14px", color: "var(--muted)", margin: "0 0 24px 0" }}>
          How the 4 components work together to take an underperforming channel from diagnosis to audience revival.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "16px", position: "relative" }}>
          <div style={{ background: "var(--surface-2)", padding: "18px", borderRadius: "12px", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#3b82f6", marginBottom: "6px" }}>STEP 1 · DIAGNOSIS</div>
            <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>Growth Velocity Deficit</h4>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
              <strong>Component 1</strong> identifies lagging channels by comparing views/subscribers and growth percentiles against niche peers.
            </p>
          </div>

          <div style={{ background: "var(--surface-2)", padding: "18px", borderRadius: "12px", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#10b981", marginBottom: "6px" }}>STEP 2 · DEMAND ANALYSIS</div>
            <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>Audience Content Gap</h4>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
              <strong>Component 2</strong> mines public comments to quantify unmet audience demand and computes supply-demand divergence.
            </p>
          </div>

          <div style={{ background: "var(--surface-2)", padding: "18px", borderRadius: "12px", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#ec4899", marginBottom: "6px" }}>STEP 3 · TOPIC MOMENTUM</div>
            <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>Emerging Changepoints</h4>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
              <strong>Component 4</strong> detects structural upward shifts in content topics using BOCPD with hierarchical Bayesian stabilization.
            </p>
          </div>

          <div style={{ background: "var(--surface-2)", padding: "18px", borderRadius: "12px", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#8b5cf6", marginBottom: "6px" }}>STEP 4 · AUDIENCE TRANSFER</div>
            <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>Bridge Cross-Promotion</h4>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" }}>
              <strong>Component 3</strong> routes audience attention from top flagship channels to underperforming channels via diffusion bridges.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
