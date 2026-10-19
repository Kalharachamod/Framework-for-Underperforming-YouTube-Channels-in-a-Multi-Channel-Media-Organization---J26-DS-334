import React, { useState } from "react";
import { Link } from "react-router-dom";
import { LandingNavbar } from "./LandingNavbar";
import { VidIQSpyWidget } from "./VidIQSpyWidget";
import { PricingSection } from "./PricingSection";
import { LandingFooter } from "./LandingFooter";
import { AuthModal } from "./AuthModal";

export const HomePage: React.FC = () => {
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [user, setUser] = useState<{ name: string; email: string; avatar?: string } | null>(null);

  return (
    <div className="landing-page">
      {/* Ambient background glow elements */}
      <div className="ambient-glow-top" />
      <div className="ambient-glow-side" />

      {/* Modern Landing Navbar */}
      <LandingNavbar
        user={user}
        onOpenAuth={() => setAuthModalOpen(true)}
        onSignOut={() => setUser(null)}
      />

      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-pill">
          <span className="pulse-dot" />
          <span>SLIIT CoEAI RESEARCH · J26-DS-334</span>
        </div>

        <h1 className="hero-headline">
          Revive Underperforming YouTube Channels with{" "}
          <span className="gradient-text">Multi-Channel AI Intelligence</span>
        </h1>

        <p className="hero-subtitle">
          The first data science framework engineered specifically for multi-channel broadcasting organizations
          (Derana, Sirasa, Hiru). Combines Bayesian changepoint forecasting, graph neural diffusion, and quantified
          audience demand mining.
        </p>

        <div className="hero-cta-group">
          <Link to="/c4/emerging-topics" className="btn-primary" style={{ fontSize: "16px", padding: "14px 28px" }}>
            Launch Research Studio ★
          </Link>
          <a href="#inspector" className="btn-secondary" style={{ fontSize: "16px", padding: "14px 28px" }}>
            Interactive Diagnostic Engine ↓
          </a>
        </div>

        {/* Live Network Trust Ticker */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "16px",
            maxWidth: "1050px",
            margin: "0 auto",
            padding: "20px 24px",
            background: "rgba(22, 32, 53, 0.4)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            backdropFilter: "blur(10px)",
          }}
        >
          <div>
            <div style={{ fontSize: "24px", fontWeight: 900, color: "#ffffff" }}>52 Channels</div>
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>Derana Media Network</div>
          </div>
          <div>
            <div style={{ fontSize: "24px", fontWeight: 900, color: "#60a5fa" }}>31.9M+</div>
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>Combined Public Subscribers</div>
          </div>
          <div>
            <div style={{ fontSize: "24px", fontWeight: 900, color: "#34d399" }}>1,682 Videos</div>
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>Shorts & Long-form Corpus</div>
          </div>
          <div>
            <div style={{ fontSize: "24px", fontWeight: 900, color: "#f472b6" }}>26,513 Comments</div>
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>Mined Viewer Feedback</div>
          </div>
        </div>
      </section>

      {/* Interactive VidIQ-style Diagnostic Tool */}
      <section id="inspector" style={{ padding: "0 24px" }}>
        <VidIQSpyWidget />
      </section>

      {/* 4 Research Pillars Deep Dive */}
      <section style={{ maxWidth: "1400px", margin: "0 auto 90px", padding: "0 24px" }}>
        <div style={{ textAlign: "center", marginBottom: "48px" }}>
          <span style={{ fontSize: "12px", fontWeight: 700, color: "#60a5fa", textTransform: "uppercase", letterSpacing: "1px" }}>
            SPECIALIZED RESEARCH DASHBOARDS
          </span>
          <h2 style={{ fontSize: "36px", fontWeight: 900, margin: "8px 0 12px 0", color: "#ffffff", letterSpacing: "-0.5px" }}>
            4 Dedicated Intelligence Dashboards
          </h2>
          <p style={{ fontSize: "16px", color: "#94a3b8", maxWidth: "700px", margin: "0 auto", lineHeight: "1.6" }}>
            Each component features its own dedicated workspace, custom sidebar, and specialized machine learning models.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))", gap: "24px" }}>
          {/* Pillar 1 */}
          <div className="glass-card" style={{ padding: "32px", borderTop: "4px solid #3b82f6", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "10px", background: "rgba(59, 130, 246, 0.2)", color: "#60a5fa" }}>
                  PILLAR 1 · DASHBOARD
                </span>
                <span style={{ fontSize: "12px", color: "#94a3b8" }}>IT23333802</span>
              </div>
              <h3 style={{ fontSize: "20px", fontWeight: 800, margin: "0 0 10px 0", color: "#ffffff" }}>
                Channel Growth Prediction
              </h3>
              <p style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.6", margin: "0 0 20px 0" }}>
                Channel-specific growth opportunity prediction with similarity-weighted pooled learning. Normalizes views/subscribers and engagement velocities via XGBoost & LightGBM.
              </p>
              <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: "12px", borderRadius: "8px", fontSize: "12px", color: "#cbd5e1", marginBottom: "20px" }}>
                <div><strong>Lead:</strong> Samarasinghe S I</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> Pooled Trees, SHAP Values</div>
              </div>
            </div>
            <Link to="/c1/growth-prediction" className="btn-secondary" style={{ width: "100%", justifyContent: "center" }}>
              Enter Pillar 1 Dashboard →
            </Link>
          </div>

          {/* Pillar 2 */}
          <div className="glass-card" style={{ padding: "32px", borderTop: "4px solid #10b981", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "10px", background: "rgba(16, 185, 129, 0.2)", color: "#34d399" }}>
                  PILLAR 2 · DASHBOARD
                </span>
                <span style={{ fontSize: "12px", color: "#94a3b8" }}>IT23307094</span>
              </div>
              <h3 style={{ fontSize: "20px", fontWeight: 800, margin: "0 0 10px 0", color: "#ffffff" }}>
                Audience Demand Mining
              </h3>
              <p style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.6", margin: "0 0 20px 0" }}>
                Quantified audience demand mining across 26,500+ comments with multilingual Sinhala-English NLP, intent classification, and Jensen-Shannon content-gap divergence.
              </p>
              <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: "12px", borderRadius: "8px", fontSize: "12px", color: "#cbd5e1", marginBottom: "20px" }}>
                <div><strong>Lead:</strong> Kahandawa K A N N</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> Multilingual NLP, JS Divergence</div>
              </div>
            </div>
            <Link to="/c2/demand-mining" className="btn-secondary" style={{ width: "100%", justifyContent: "center" }}>
              Enter Pillar 2 Dashboard →
            </Link>
          </div>

          {/* Pillar 3 */}
          <div className="glass-card" style={{ padding: "32px", borderTop: "4px solid #8b5cf6", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "10px", background: "rgba(139, 92, 246, 0.2)", color: "#a78bfa" }}>
                  PILLAR 3 · DASHBOARD
                </span>
                <span style={{ fontSize: "12px", color: "#94a3b8" }}>IT23200760</span>
              </div>
              <h3 style={{ fontSize: "20px", fontWeight: 800, margin: "0 0 10px 0", color: "#ffffff" }}>
                Audience Bridge Intelligence
              </h3>
              <p style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.6", margin: "0 0 20px 0" }}>
                Diffusion-based cross-channel audience bridge scoring. Builds a heterogeneous network graph, trains metapath2vec & HGT embeddings, and executes Personalized PageRank.
              </p>
              <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: "12px", borderRadius: "8px", fontSize: "12px", color: "#cbd5e1", marginBottom: "20px" }}>
                <div><strong>Lead:</strong> Koonara K M K C</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> HGT, PageRank Diffusion, Baselines</div>
              </div>
            </div>
            <Link to="/c3/audience-bridges" className="btn-secondary" style={{ width: "100%", justifyContent: "center" }}>
              Enter Pillar 3 Dashboard →
            </Link>
          </div>

          {/* Pillar 4 */}
          <div
            className="glass-card"
            style={{
              padding: "32px",
              borderTop: "4px solid #ec4899",
              background: "linear-gradient(180deg, rgba(30, 27, 75, 0.8) 0%, rgba(22, 32, 53, 0.85) 100%)",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              boxShadow: "0 10px 30px rgba(236, 72, 153, 0.2)",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span style={{ fontSize: "11px", fontWeight: 800, padding: "3px 8px", borderRadius: "10px", background: "rgba(236, 72, 153, 0.25)", color: "#f472b6" }}>
                  PILLAR 4 · ACTIVE LIVE ★
                </span>
                <span style={{ fontSize: "12px", color: "#f472b6", fontWeight: 700 }}>IT23323452</span>
              </div>
              <h3 style={{ fontSize: "20px", fontWeight: 800, margin: "0 0 10px 0", color: "#ffffff" }}>
                Dynamic Topic Intelligence
              </h3>
              <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: "1.6", margin: "0 0 20px 0" }}>
                Hierarchically Pooled Dynamic Topic Modelling with Bayesian Online Changepoint Detection (BOCPD).
                Empirical Bayes shrinkage cuts false trend alarms from 44.8% to 20.0% with 95% Credible Intervals.
              </p>
              <div style={{ background: "rgba(0, 0, 0, 0.4)", padding: "12px", borderRadius: "8px", fontSize: "12px", color: "#fbcfe8", marginBottom: "20px", border: "1px solid rgba(236, 72, 153, 0.3)" }}>
                <div><strong>Lead:</strong> Sankalpa H D T P (Tharuksha)</div>
                <div style={{ marginTop: "4px" }}><strong>Core Models:</strong> Hierarchical Bayes, BOCPD Engine</div>
              </div>
            </div>
            <Link to="/c4/emerging-topics" className="btn-primary" style={{ width: "100%", justifyContent: "center" }}>
              Enter Pillar 4 Studio (Live) ★
            </Link>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <PricingSection onOpenAuth={() => setAuthModalOpen(true)} />

      {/* Modern Landing Footer */}
      <LandingFooter />

      {/* Interactive Auth Modal */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onLoginSuccess={(loggedUser) => setUser(loggedUser)}
      />
    </div>
  );
};
