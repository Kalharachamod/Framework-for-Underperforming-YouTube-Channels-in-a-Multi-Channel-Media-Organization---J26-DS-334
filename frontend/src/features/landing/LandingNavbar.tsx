import React, { useState } from "react";
import { Link } from "react-router-dom";

interface UserProfile {
  name: string;
  email: string;
  avatar?: string;
}

interface LandingNavbarProps {
  user: UserProfile | null;
  onOpenAuth: () => void;
  onSignOut: () => void;
}

export const LandingNavbar: React.FC<LandingNavbarProps> = ({ user, onOpenAuth, onSignOut }) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);

  return (
    <header className="landing-nav">
      <div className="landing-nav__container">
        {/* Brand */}
        <Link to="/" className="landing-nav__brand">
          <div className="landing-nav__logo">T</div>
          <div className="landing-nav__title">
            <span>Trendora AI</span>
            <span className="landing-nav__badge">Growth Intelligence</span>
          </div>
        </Link>

        {/* Center Links */}
        <nav>
          <ul className="landing-nav__links">
            <li>
              <div style={{ position: "relative" }}>
                <button
                  type="button"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                  className="landing-nav__link"
                  style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                >
                  <span>4 Research Pillars</span>
                  <span style={{ fontSize: "10px" }}>▼</span>
                </button>

                {dropdownOpen && (
                  <div
                    style={{
                      position: "absolute",
                      top: "calc(100% + 14px)",
                      left: "-20px",
                      width: "320px",
                      background: "#111827",
                      border: "1px solid rgba(255, 255, 255, 0.12)",
                      borderRadius: "14px",
                      padding: "12px",
                      boxShadow: "0 15px 35px rgba(0, 0, 0, 0.6)",
                      zIndex: 200,
                      display: "flex",
                      flexDirection: "column",
                      gap: "8px",
                    }}
                  >
                    <Link
                      to="/c1/growth-prediction"
                      onClick={() => setDropdownOpen(false)}
                      style={{
                        display: "block",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        textDecoration: "none",
                        color: "#ffffff",
                        background: "rgba(255, 255, 255, 0.04)",
                      }}
                    >
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#60a5fa" }}>Pillar 1: Growth Prediction</div>
                      <div style={{ fontSize: "11px", color: "#94a3b8" }}>Pooled XGBoost / LightGBM velocity scoring</div>
                    </Link>

                    <Link
                      to="/c2/demand-mining"
                      onClick={() => setDropdownOpen(false)}
                      style={{
                        display: "block",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        textDecoration: "none",
                        color: "#ffffff",
                        background: "rgba(255, 255, 255, 0.04)",
                      }}
                    >
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#34d399" }}>Pillar 2: Audience Demand</div>
                      <div style={{ fontSize: "11px", color: "#94a3b8" }}>26.5k Comment Mining & Jensen-Shannon Gap</div>
                    </Link>

                    <Link
                      to="/c3/audience-bridges"
                      onClick={() => setDropdownOpen(false)}
                      style={{
                        display: "block",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        textDecoration: "none",
                        color: "#ffffff",
                        background: "rgba(255, 255, 255, 0.04)",
                      }}
                    >
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#a78bfa" }}>Pillar 3: Audience Bridges</div>
                      <div style={{ fontSize: "11px", color: "#94a3b8" }}>Heterogeneous Graph & PageRank Diffusion</div>
                    </Link>

                    <Link
                      to="/c4/emerging-topics"
                      onClick={() => setDropdownOpen(false)}
                      style={{
                        display: "block",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        textDecoration: "none",
                        color: "#ffffff",
                        background: "rgba(236, 72, 153, 0.12)",
                        border: "1px solid rgba(236, 72, 153, 0.3)",
                      }}
                    >
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#f472b6" }}>Pillar 4: Emerging Topics (Live) ★</div>
                      <div style={{ fontSize: "11px", color: "#fbcfe8" }}>Bayesian Online Changepoints (BOCPD)</div>
                    </Link>
                  </div>
                )}
              </div>
            </li>
            <li>
              <a href="#inspector" className="landing-nav__link">
                Diagnostic Tool
              </a>
            </li>
            <li>
              <a href="#pricing" className="landing-nav__link">
                Pricing
              </a>
            </li>
            <li>
              <Link to="/status" className="landing-nav__link">
                <span>System Status</span>
                <span className="pulse-dot" style={{ width: "6px", height: "6px" }} />
              </Link>
            </li>
          </ul>
        </nav>

        {/* Right Actions */}
        <div className="landing-nav__actions">
          {user ? (
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{ textAlign: "right", display: "none" /* hide text on tiny screens */ }}>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "#ffffff" }}>{user.name}</div>
                <div style={{ fontSize: "11px", color: "#94a3b8" }}>{user.email}</div>
              </div>
              {user.avatar ? (
                <img
                  src={user.avatar}
                  alt={user.name}
                  style={{ width: "36px", height: "36px", borderRadius: "50%", border: "2px solid #8b5cf6" }}
                />
              ) : (
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "50%",
                    background: "#8b5cf6",
                    color: "#ffffff",
                    display: "grid",
                    placeItems: "center",
                    fontWeight: 700,
                  }}
                >
                  {user.name.charAt(0)}
                </div>
              )}
              <button
                type="button"
                onClick={onSignOut}
                className="btn-secondary"
                style={{ padding: "6px 12px", fontSize: "12px" }}
              >
                Sign Out
              </button>
              <Link to="/c4/emerging-topics" className="btn-primary" style={{ padding: "8px 16px" }}>
                Studio Dashboard →
              </Link>
            </div>
          ) : (
            <>
              <button type="button" onClick={onOpenAuth} className="btn-secondary">
                Sign In
              </button>
              <button type="button" onClick={onOpenAuth} className="btn-primary">
                Get Started Free
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
