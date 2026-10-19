import React from "react";
import { Link } from "react-router-dom";

export const ContentGapPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "20px" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#fef3c7", color: "#b45309", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          EXPERIMENTAL VALIDATION · PILLAR 2
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Content-Gap Divergence (Supply vs Demand)
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Jensen-Shannon Divergence measuring discrepancy between video upload topics and audience comment demand
        </p>
      </div>

      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Niche Supply-Demand Divergence Index (JSD)</h3>
        <p style={{ margin: "0 0 16px 0", fontSize: "13px", color: "var(--muted)" }}>
          Higher divergence values indicate high unmet viewer demand where channel production is not satisfying audience requests.
        </p>

        <table className="table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
              <th style={{ padding: "10px" }}>Niche Cluster</th>
              <th style={{ padding: "10px", textAlign: "right" }}>Video Supply Share</th>
              <th style={{ padding: "10px", textAlign: "right" }}>Audience Demand Share</th>
              <th style={{ padding: "10px", textAlign: "center" }}>JSD Divergence</th>
              <th style={{ padding: "10px" }}>Operational Prescription</th>
            </tr>
          </thead>
          <tbody>
            {[
              { niche: "Special Interest / Investigative", supply: "8.2%", demand: "24.5%", jsd: "0.412", alert: "High Gap: Severe under-supply of investigative content", severe: true },
              { niche: "Music & Acoustic Covers", supply: "14.1%", demand: "26.8%", jsd: "0.328", alert: "Moderate Gap: Viewers demanding uncut acoustic versions", severe: false },
              { niche: "Entertainment & Reality", supply: "42.0%", demand: "31.2%", jsd: "0.184", alert: "Over-Saturated: High video volume, audience fatigue", severe: false },
              { niche: "News & Current Affairs", supply: "28.5%", demand: "25.0%", jsd: "0.076", alert: "Balanced: Video production closely tracks public interest", severe: false },
            ].map((row) => (
              <tr key={row.niche} style={{ borderBottom: "1px solid #f1f5f9", background: row.severe ? "#fff1f2" : "transparent" }}>
                <td style={{ padding: "12px 10px", fontWeight: 600 }}>{row.niche}</td>
                <td style={{ padding: "12px 10px", textAlign: "right" }}>{row.supply}</td>
                <td style={{ padding: "12px 10px", textAlign: "right", fontWeight: 700, color: row.severe ? "#be123c" : "inherit" }}>{row.demand}</td>
                <td style={{ padding: "12px 10px", textAlign: "center", fontFamily: "monospace", fontWeight: 700 }}>{row.jsd}</td>
                <td style={{ padding: "12px 10px", fontSize: "12px", color: row.severe ? "#be123c" : "#64748b" }}>{row.alert}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: "12px" }}>
        <Link to="/audience-demand" className="button" style={{ textDecoration: "none" }}>
          ← Back to Demand Mining
        </Link>
      </div>
    </div>
  );
};
