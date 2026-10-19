import React from "react";
import { Link } from "react-router-dom";

export const MultilingualNlpPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#d1fae5", color: "#065f46", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          MULTILINGUAL NLP PREPROCESSING · PILLAR 2
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "#0f172a" }}>
          Sinhala-English-Tanglish Normalization Pipeline
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Processing 26,513 Multi-Script Audience Comments with Zero Data Leakage and Pseudonymization
        </p>
      </div>

      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Language Classification Breakdown</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
          <div style={{ background: "#f8fafc", padding: "16px", borderRadius: "10px", borderLeft: "3px solid #10b981" }}>
            <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>Pure Sinhala Unicode</div>
            <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", margin: "4px 0" }}>44.2%</div>
            <div style={{ fontSize: "12px", color: "#64748b" }}>11,718 comments normalized</div>
          </div>

          <div style={{ background: "#f8fafc", padding: "16px", borderRadius: "10px", borderLeft: "3px solid #3b82f6" }}>
            <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>Code-Mixed Tanglish</div>
            <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", margin: "4px 0" }}>28.3%</div>
            <div style={{ fontSize: "12px", color: "#64748b" }}>7,503 phonetic Romanized comments</div>
          </div>

          <div style={{ background: "#f8fafc", padding: "16px", borderRadius: "10px", borderLeft: "3px solid #8b5cf6" }}>
            <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>Standard English</div>
            <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", margin: "4px 0" }}>27.5%</div>
            <div style={{ fontSize: "12px", color: "#64748b" }}>7,292 comments</div>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: "10px" }}>
        <Link to="/c2/demand-mining" className="button" style={{ textDecoration: "none" }}>
          ← Back to Demand Mining
        </Link>
        <Link to="/c2/content-gap" className="button" style={{ textDecoration: "none" }}>
          View Content-Gap Divergence →
        </Link>
      </div>
    </div>
  );
};
