import React, { useState } from "react";

interface PricingSectionProps {
  onOpenAuth: () => void;
}

export const PricingSection: React.FC<PricingSectionProps> = ({ onOpenAuth }) => {
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("yearly");

  return (
    <section id="pricing" className="pricing-section">
      <div style={{ maxWidth: "700px", margin: "0 auto 32px" }}>
        <span
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: "#a78bfa",
            textTransform: "uppercase",
            letterSpacing: "1px",
            display: "inline-block",
            marginBottom: "8px",
          }}
        >
          PLANS & ACCESS TIERS
        </span>
        <h2 style={{ fontSize: "36px", fontWeight: 900, margin: "0 0 12px 0", color: "#ffffff", letterSpacing: "-0.5px" }}>
          Transparent Pricing for Creators & Media Networks
        </h2>
        <p style={{ fontSize: "16px", color: "#94a3b8", lineHeight: "1.6", margin: 0 }}>
          From free academic research access to enterprise multi-channel revival suites for major television networks.
        </p>

        {/* Billing Switcher */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "10px",
            background: "rgba(255, 255, 255, 0.06)",
            padding: "4px",
            borderRadius: "30px",
            marginTop: "24px",
            border: "1px solid rgba(255, 255, 255, 0.1)",
          }}
        >
          <button
            type="button"
            onClick={() => setBillingCycle("monthly")}
            style={{
              padding: "8px 18px",
              borderRadius: "20px",
              border: "none",
              background: billingCycle === "monthly" ? "var(--brand-gradient)" : "transparent",
              color: "#ffffff",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            Monthly
          </button>
          <button
            type="button"
            onClick={() => setBillingCycle("yearly")}
            style={{
              padding: "8px 18px",
              borderRadius: "20px",
              border: "none",
              background: billingCycle === "yearly" ? "var(--brand-gradient)" : "transparent",
              color: "#ffffff",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              transition: "all 0.2s",
            }}
          >
            <span>Annual</span>
            <span style={{ fontSize: "10px", background: "#10b981", color: "#ffffff", padding: "2px 6px", borderRadius: "10px", fontWeight: 700 }}>
              SAVE 20%
            </span>
          </button>
        </div>
      </div>

      {/* Pricing Cards Grid */}
      <div className="pricing-grid">
        {/* Tier 1: Researcher */}
        <div className="pricing-card">
          <div>
            <div style={{ fontSize: "12px", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>Academic</div>
            <h3 style={{ fontSize: "22px", fontWeight: 800, margin: "6px 0 12px 0", color: "#ffffff" }}>Researcher Free</h3>
            <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginBottom: "16px" }}>
              <span style={{ fontSize: "40px", fontWeight: 900, color: "#ffffff" }}>$0</span>
              <span style={{ fontSize: "14px", color: "#94a3b8" }}>forever</span>
            </div>
            <p style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.5", margin: "0 0 24px 0" }}>
              Full open access to published research snapshots and read-only baseline benchmarks for university researchers.
            </p>

            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "13px", color: "#cbd5e1", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li>✓ Access to 52 portfolio channels</li>
              <li>✓ 15 Dynamic Topic trajectories</li>
              <li>✓ Basic BOCPD changepoint flags</li>
              <li>✓ Downloadable Parquet snapshots</li>
              <li>✓ Open research methodology docs</li>
            </ul>
          </div>

          <button
            type="button"
            onClick={onOpenAuth}
            className="btn-secondary"
            style={{ width: "100%", justifyContent: "center", marginTop: "28px" }}
          >
            Get Free Access
          </button>
        </div>

        {/* Tier 2: Creator Pro (Featured) */}
        <div className="pricing-card featured">
          <div
            style={{
              position: "absolute",
              top: "-12px",
              left: "50%",
              transform: "translateX(-50%)",
              background: "var(--brand-gradient)",
              padding: "4px 14px",
              borderRadius: "20px",
              fontSize: "11px",
              fontWeight: 800,
              color: "#ffffff",
              letterSpacing: "0.5px",
              boxShadow: "0 4px 12px rgba(139, 92, 246, 0.5)",
            }}
          >
            MOST POPULAR FOR CREATORS
          </div>

          <div>
            <div style={{ fontSize: "12px", fontWeight: 700, color: "#a78bfa", textTransform: "uppercase" }}>Channel Pro</div>
            <h3 style={{ fontSize: "22px", fontWeight: 800, margin: "6px 0 12px 0", color: "#ffffff" }}>Creator Studio Pro</h3>
            <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginBottom: "16px" }}>
              <span style={{ fontSize: "40px", fontWeight: 900, color: "#ffffff" }}>
                ${billingCycle === "yearly" ? "24" : "29"}
              </span>
              <span style={{ fontSize: "14px", color: "#94a3b8" }}>/ month</span>
            </div>
            <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: "1.5", margin: "0 0 24px 0" }}>
              Comprehensive real-time topic momentum and growth alerts for growing independent YouTube channels.
            </p>

            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "13px", color: "#ffffff", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li>✓ <strong>Live Bayesian Changepoint Detection (BOCPD)</strong></li>
              <li>✓ 95% Credible Interval risk projections</li>
              <li>✓ Single-channel views/subscriber growth scoring</li>
              <li>✓ Audience comment demand intent classifier</li>
              <li>✓ 2 Recommended audience bridge channels</li>
              <li>✓ Email trend alert notifications</li>
            </ul>
          </div>

          <button
            type="button"
            onClick={onOpenAuth}
            className="btn-primary"
            style={{ width: "100%", justifyContent: "center", marginTop: "28px" }}
          >
            Start 14-Day Free Trial
          </button>
        </div>

        {/* Tier 3: Enterprise Media Network */}
        <div className="pricing-card">
          <div>
            <div style={{ fontSize: "12px", fontWeight: 700, color: "#34d399", textTransform: "uppercase" }}>Enterprise</div>
            <h3 style={{ fontSize: "22px", fontWeight: 800, margin: "6px 0 12px 0", color: "#ffffff" }}>Media Network MCN</h3>
            <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginBottom: "16px" }}>
              <span style={{ fontSize: "40px", fontWeight: 900, color: "#ffffff" }}>
                ${billingCycle === "yearly" ? "159" : "199"}
              </span>
              <span style={{ fontSize: "14px", color: "#94a3b8" }}>/ month</span>
            </div>
            <p style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.5", margin: "0 0 24px 0" }}>
              Built for broadcasting networks (Derana, Sirasa, Hiru) managing multiple subsidiary channels.
            </p>

            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "13px", color: "#cbd5e1", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li>✓ <strong>Unlimited Multi-Channel Portfolio (50+ Channels)</strong></li>
              <li>✓ Heterogeneous Graph Neural Diffusion (HGT)</li>
              <li>✓ Full Cross-Channel Audience Bridge Score Matrix</li>
              <li>✓ Pooled Niche Bayesian Shrinkage Engine</li>
              <li>✓ Content-Gap Jensen-Shannon Divergence Map</li>
              <li>✓ Direct PostgreSQL / Supabase sync</li>
              <li>✓ Priority CoEAI Engineering Support</li>
            </ul>
          </div>

          <button
            type="button"
            onClick={onOpenAuth}
            className="btn-secondary"
            style={{ width: "100%", justifyContent: "center", marginTop: "28px" }}
          >
            Schedule Media Org Demo
          </button>
        </div>
      </div>
    </section>
  );
};
