import React from "react";
import { Link } from "react-router-dom";

export const LandingFooter: React.FC = () => {
  return (
    <footer style={{ background: "#060911", borderTop: "1px solid rgba(255, 255, 255, 0.08)", padding: "70px 24px 40px" }}>
      <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "40px", marginBottom: "60px" }}>
          {/* Column 1: Brand & Project */}
          <div style={{ maxWidth: "340px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
              <div
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  background: "var(--brand-gradient)",
                  display: "grid",
                  placeItems: "center",
                  fontWeight: 800,
                  color: "#ffffff",
                }}
              >
                T
              </div>
              <span style={{ fontSize: "18px", fontWeight: 800, color: "#ffffff" }}>Trendora AI</span>
            </div>
            <p style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.6", margin: "0 0 16px 0" }}>
              Growth Intelligence Framework for Underperforming YouTube Channels in a Multi-Channel Media Organization.
            </p>
            <div style={{ fontSize: "12px", color: "#64748b" }}>
              SLIIT Centre of Excellence in AI (CoEAI) · J26-DS-334
            </div>
          </div>

          {/* Column 2: 4 Research Pillars */}
          <div>
            <h4 style={{ fontSize: "14px", fontWeight: 700, color: "#ffffff", margin: "0 0 16px 0", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              4 Research Pillars
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "13px", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li>
                <Link to="/c1/growth-prediction" style={{ color: "#94a3b8", textDecoration: "none" }}>
                  Pillar 1: Growth Prediction (IT23333802)
                </Link>
              </li>
              <li>
                <Link to="/c2/demand-mining" style={{ color: "#94a3b8", textDecoration: "none" }}>
                  Pillar 2: Audience Demand (IT23307094)
                </Link>
              </li>
              <li>
                <Link to="/c3/audience-bridges" style={{ color: "#94a3b8", textDecoration: "none" }}>
                  Pillar 3: Audience Bridges (IT23200760)
                </Link>
              </li>
              <li>
                <Link to="/c4/emerging-topics" style={{ color: "#f472b6", textDecoration: "none", fontWeight: 600 }}>
                  Pillar 4: Topic Dynamics (IT23323452) ★
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3: Scientific Methodology */}
          <div>
            <h4 style={{ fontSize: "14px", fontWeight: 700, color: "#ffffff", margin: "0 0 16px 0", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Methodology
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "13px", color: "#94a3b8", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li>Bayesian Online Changepoints (BOCPD)</li>
              <li>Empirical Bayes Partial Pooling</li>
              <li>Heterogeneous Graph Transformer (HGT)</li>
              <li>Personalized PageRank Diffusion</li>
              <li>Jensen-Shannon Content-Gap Divergence</li>
              <li>Multilingual Sinhala/English Text Cleaning</li>
            </ul>
          </div>

          {/* Column 4: Platform & Data */}
          <div>
            <h4 style={{ fontSize: "14px", fontWeight: 700, color: "#ffffff", margin: "0 0 16px 0", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Data & Platform
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "13px", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li>
                <Link to="/channels" style={{ color: "#94a3b8", textDecoration: "none" }}>
                  52 Monitored Channels Portfolio
                </Link>
              </li>
              <li>
                <Link to="/status" style={{ color: "#94a3b8", textDecoration: "none" }}>
                  Active Snapshot (rs-20261018T210855Z)
                </Link>
              </li>
              <li>
                <span style={{ color: "#64748b" }}>Derana Media Network Partner</span>
              </li>
              <li>
                <span style={{ color: "#64748b" }}>PostgreSQL & DuckDB High-Speed Lake</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            paddingTop: "24px",
            borderTop: "1px solid rgba(255, 255, 255, 0.06)",
            fontSize: "12px",
            color: "#64748b",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>© 2026 Trendora Research Platform · SLIIT Data Science Specialization · All rights reserved.</div>
          <div style={{ display: "flex", gap: "20px" }}>
            <span>Privacy Protocol</span>
            <span>Security</span>
            <span>Ethics & Pseudonymization</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
