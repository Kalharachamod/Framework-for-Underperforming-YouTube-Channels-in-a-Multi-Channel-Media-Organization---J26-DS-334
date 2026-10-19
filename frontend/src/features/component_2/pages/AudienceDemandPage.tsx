import React from "react";
import { Link } from "react-router-dom";

export const AudienceDemandPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#d1fae5", color: "#065f46", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          RESEARCH PILLAR 2 · IT23307094
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Audience Demand Mining & Intent Classification
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Mining Public Comments to Quantify Unmet Audience Content Demand and Intent Signals
        </p>
      </div>

      {/* KPI Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #10b981" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Mined Comments</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>26,513</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>52 Network Channels</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #3b82f6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Audience Cohort</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>16,976</div>
          <div style={{ fontSize: "12px", color: "#16a34a", fontWeight: 600 }}>Unique Pseudonymized Viewers</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #f59e0b" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Language Mix</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>72.5%</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Sinhala / English / Tanglish</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #8b5cf6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>Demand Intents</div>
          <div style={{ fontSize: "24px", fontWeight: 800, margin: "4px 0" }}>5 Categories</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Requests, Critiques, Feedback</div>
        </div>
      </div>

      {/* Demand Intent Distribution Card */}
      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Audience Intent Breakdown</h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--muted)" }}>
              Distribution of public YouTube comment intentions extracted across portfolio channels.
            </p>
          </div>
          <Link to="/content-gap" style={{ fontSize: "13px", fontWeight: 600, color: "#059669", textDecoration: "none" }}>
            View Content-Gap Divergence →
          </Link>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
          {[
            { intent: "Content Requests & Inquiries", pct: "34.2%", count: "9,067", color: "#10b981", desc: "Viewers requesting specific topics, actors, songs, or coverage" },
            { intent: "Appreciation & Positive Feedback", pct: "38.6%", count: "10,234", color: "#3b82f6", desc: "Expressions of praise, support, and community loyalty" },
            { intent: "Constructive Critique", pct: "14.8%", count: "3,924", color: "#f59e0b", desc: "Feedback on audio, presentation quality, or video pacing" },
            { intent: "Questions & Engagement", pct: "8.1%", count: "2,148", color: "#8b5cf6", desc: "Follow-up questions regarding video content" },
            { intent: "Filtered Noise / Spam", pct: "4.3%", count: "1,140", color: "#ef4444", desc: "Automated promotional bots and irrelevant comments" },
          ].map((item) => (
            <div key={item.intent} style={{ background: "var(--surface-2)", padding: "16px", borderRadius: "10px", borderLeft: `3px solid ${item.color}` }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: item.color, textTransform: "uppercase" }}>{item.pct}</div>
              <h4 style={{ margin: "4px 0", fontSize: "14px", fontWeight: 700 }}>{item.intent}</h4>
              <div style={{ fontSize: "12px", color: "var(--muted)", margin: "4px 0" }}>{item.count} comments</div>
              <p style={{ margin: 0, fontSize: "11px", color: "var(--muted)", lineHeight: "1.4" }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Methodology Section */}
      <div className="card" style={{ padding: "24px" }}>
        <h3 style={{ margin: "0 0 12px 0", fontSize: "17px", fontWeight: 700 }}>🔬 Research Methodology</h3>
        <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "14px", lineHeight: "1.8", color: "#334155" }}>
          <li>
            <strong>Multilingual Preprocessing:</strong> Normalized Sinhala Unicode representations, transliterated Tanglish phrases, and handled punctuation/emojis across 26,513 raw comments.
          </li>
          <li>
            <strong>Demand Intent Annotation Protocol:</strong> Stratified random sampling using deterministic MD5 hashes across video tiers to label demand requests vs general chit-chat.
          </li>
          <li>
            <strong>Privacy Preservation:</strong> Cryptographic one-way hashing with confidential organizational salt for all viewer IDs prior to analysis.
          </li>
        </ul>
      </div>
    </div>
  );
};
