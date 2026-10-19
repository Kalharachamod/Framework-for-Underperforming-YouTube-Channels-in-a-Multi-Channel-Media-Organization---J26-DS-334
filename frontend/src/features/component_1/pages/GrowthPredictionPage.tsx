import React from "react";
import { Link } from "react-router-dom";

export const GrowthPredictionPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#dbeafe", color: "#1d4ed8", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          RESEARCH PILLAR 1 · IT23333802
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Channel Growth Opportunity Prediction
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Similarity-Weighted Pooled Learning across Niche Groups for Underperforming Channel Growth Forecasts
        </p>
      </div>

      {/* KPI Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #3b82f6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Monitored Portfolio</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>52 Channels</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Derana Media Network</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #10b981" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Observation Corpus</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>1,682 Videos</div>
          <div style={{ fontSize: "12px", color: "#16a34a", fontWeight: 600 }}>Normalized Indicators</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #8b5cf6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Pooling Strategy</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>Niche-Similarity</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>6 Functional Niche Clusters</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #f59e0b" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Candidate Models</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>XGBoost / LightGBM</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>SHAP Feature Importance</div>
        </div>
      </div>

      {/* Main Analysis Card */}
      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Channel-Specific Growth Opportunity Matrix</h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--muted)" }}>
              Predictive growth classification based on views/subscriber velocity, engagement ratios, and pooled group priors.
            </p>
          </div>
          <Link to="/growth-evaluation" style={{ fontSize: "13px", fontWeight: 600, color: "#2563eb", textDecoration: "none" }}>
            View Model Evaluation & SHAP →
          </Link>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
                <th style={{ padding: "10px" }}>Channel Name</th>
                <th style={{ padding: "10px" }}>Niche Group</th>
                <th style={{ padding: "10px", textAlign: "right" }}>Subscribers</th>
                <th style={{ padding: "10px", textAlign: "right" }}>Views / Sub</th>
                <th style={{ padding: "10px", textAlign: "center" }}>Growth Potential</th>
                <th style={{ padding: "10px", textAlign: "center" }}>Opportunity Status</th>
              </tr>
            </thead>
            <tbody>
              {[
                { name: "TV Derana", niche: "Entertainment", subs: "5.1M", vps: "0.48", prob: 88, status: "Flagship / Stable" },
                { name: "Ada Derana 24", niche: "News", subs: "1.8M", vps: "0.62", prob: 92, status: "High Momentum" },
                { name: "Derana City Of Music", niche: "Music", subs: "480K", vps: "0.22", prob: 64, status: "Moderate Opportunity" },
                { name: "eTunes", niche: "Music", subs: "120K", vps: "0.14", prob: 45, status: "Underperforming (Target)" },
                { name: "Lokaya Saha Lokayo", niche: "Entertainment", subs: "290K", vps: "0.19", prob: 58, status: "Underperforming (Target)" },
                { name: "FM Derana", niche: "News", subs: "340K", vps: "0.28", prob: 71, status: "Emerging Breakout" },
                { name: "DAM DERANA", niche: "Culture", subs: "95K", vps: "0.11", prob: 39, status: "Underperforming (Target)" },
              ].map((row) => (
                <tr key={row.name} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "12px 10px", fontWeight: 600 }}>{row.name}</td>
                  <td style={{ padding: "12px 10px", color: "var(--muted)" }}>{row.niche}</td>
                  <td style={{ padding: "12px 10px", textAlign: "right" }}>{row.subs}</td>
                  <td style={{ padding: "12px 10px", textAlign: "right", fontFamily: "monospace" }}>{row.vps}</td>
                  <td style={{ padding: "12px 10px", textAlign: "center" }}>
                    <div style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ fontWeight: 700, color: row.prob >= 70 ? "#16a34a" : row.prob >= 50 ? "#d97706" : "#dc2626" }}>
                        {row.prob}%
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: "12px 10px", textAlign: "center" }}>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: "12px",
                        fontSize: "11px",
                        fontWeight: 600,
                        background: row.status.includes("Target") ? "#fee2e2" : row.status.includes("High") ? "#dcfce7" : "#eff6ff",
                        color: row.status.includes("Target") ? "#b91c1c" : row.status.includes("High") ? "#15803d" : "#1d4ed8",
                      }}
                    >
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Methodology Section */}
      <div className="card" style={{ padding: "24px" }}>
        <h3 style={{ margin: "0 0 12px 0", fontSize: "17px", fontWeight: 700 }}>🔬 Research Methodology</h3>
        <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "14px", lineHeight: "1.8", color: "#334155" }}>
          <li>
            <strong>Normalized Growth Indicators:</strong> Calculates standardized views per subscriber, views per 24 hours post-upload, and like-to-comment ratios to remove size bias between major network channels and small portfolio channels.
          </li>
          <li>
            <strong>Pooled Cross-Channel Learning:</strong> Solves data sparsity for younger channels by transferring learned gradient boosted tree weights across niche-similar channel groupings.
          </li>
          <li>
            <strong>Model Benchmarking:</strong> Comparative evaluation between Random Forest, XGBoost, and LightGBM across time-based train-test splits.
          </li>
        </ul>
      </div>
    </div>
  );
};
