import React from "react";
import { Link } from "react-router-dom";

export const NichePoolingPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#dbeafe", color: "#1d4ed8", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          NICHE POOLING DIAGNOSTICS · PILLAR 1
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "#0f172a" }}>
          Functional Niche Clusters & Cross-Channel Weight Transfer
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Overcoming Data Sparsity for Small Subsidiary Channels via Similarity-Weighted Group Priors
        </p>
      </div>

      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Identified Niche Groupings across 52 Channels</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "16px" }}>
          {[
            { group: "News & Current Affairs", channels: "14 Channels", exemplar: "Ada Derana 24, FM Derana", color: "#ef4444" },
            { group: "Entertainment & Teledrama", channels: "18 Channels", exemplar: "TV Derana, Lokaya Saha Lokayo", color: "#f59e0b" },
            { group: "Music & Acoustic", channels: "8 Channels", exemplar: "Derana City Of Music, eTunes", color: "#8b5cf6" },
            { group: "Culture & Documentaries", channels: "5 Channels", exemplar: "DAM DERANA", color: "#10b981" },
            { group: "Lifestyle & Cooking", channels: "4 Channels", exemplar: "Ape Amma Derana Partner", color: "#06b6d4" },
            { group: "Education & Youth", channels: "3 Channels", exemplar: "Derana Little Star Edu", color: "#3b82f6" },
          ].map((item) => (
            <div key={item.group} style={{ background: "#f8fafc", padding: "16px", borderRadius: "10px", borderLeft: `3px solid ${item.color}` }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: item.color, textTransform: "uppercase" }}>{item.channels}</div>
              <h4 style={{ margin: "4px 0", fontSize: "15px", fontWeight: 700 }}>{item.group}</h4>
              <p style={{ margin: 0, fontSize: "12px", color: "#64748b" }}>Exemplars: {item.exemplar}</p>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: "10px" }}>
        <Link to="/c1/growth-prediction" className="button" style={{ textDecoration: "none" }}>
          ← Back to Growth Opportunities
        </Link>
        <Link to="/c1/growth-evaluation" className="button" style={{ textDecoration: "none" }}>
          View SHAP Feature Importance →
        </Link>
      </div>
    </div>
  );
};
