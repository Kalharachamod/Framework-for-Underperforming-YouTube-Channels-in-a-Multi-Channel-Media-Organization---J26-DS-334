import React, { useState } from "react";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoginSuccess: (user: { name: string; email: string; avatar?: string }) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, onLoginSuccess }) => {
  const [tab, setTab] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleGoogleAuth = () => {
    setLoading(true);
    // Simulate instantaneous Google OAuth sign-in with research user profile
    setTimeout(() => {
      setLoading(false);
      onLoginSuccess({
        name: "Tharuksha Sankalpa",
        email: "tharuksha@trendora.ai",
        avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=120&h=120&q=80",
      });
      onClose();
    }, 600);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      onLoginSuccess({
        name: name || email.split("@")[0],
        email: email,
      });
      onClose();
    }, 600);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Close Button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "20px",
            right: "20px",
            background: "none",
            border: "none",
            color: "#94a3b8",
            fontSize: "22px",
            cursor: "pointer",
            padding: "4px",
            lineHeight: 1,
          }}
          aria-label="Close modal"
        >
          ×
        </button>

        {/* Modal Brand Header */}
        <div style={{ textAlign: "center", marginBottom: "24px" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "12px",
              background: "var(--brand-gradient)",
              margin: "0 auto 12px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "22px",
              fontWeight: 800,
              color: "#ffffff",
              boxShadow: "0 0 20px rgba(139, 92, 246, 0.4)",
            }}
          >
            T
          </div>
          <h2 style={{ fontSize: "22px", fontWeight: 800, margin: "0 0 6px 0", color: "#ffffff" }}>
            {tab === "signin" ? "Welcome back to Trendora" : "Create your Trendora account"}
          </h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#94a3b8" }}>
            {tab === "signin"
              ? "Access all 4 research dashboards and AI intelligence models"
              : "Start diagnosing underperforming channels in minutes"}
          </p>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: "flex",
            background: "rgba(255, 255, 255, 0.06)",
            borderRadius: "10px",
            padding: "4px",
            marginBottom: "20px",
          }}
        >
          <button
            type="button"
            onClick={() => setTab("signin")}
            style={{
              flex: 1,
              padding: "8px",
              border: "none",
              borderRadius: "8px",
              background: tab === "signin" ? "#3b82f6" : "transparent",
              color: "#ffffff",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setTab("signup")}
            style={{
              flex: 1,
              padding: "8px",
              border: "none",
              borderRadius: "8px",
              background: tab === "signup" ? "#3b82f6" : "transparent",
              color: "#ffffff",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            Create Account
          </button>
        </div>

        {/* Google Authentication Button */}
        <button
          type="button"
          className="google-auth-btn"
          onClick={handleGoogleAuth}
          disabled={loading}
          style={{ marginBottom: "20px" }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            />
          </svg>
          <span>{loading ? "Connecting to Google..." : "Continue with Google"}</span>
        </button>

        {/* Divider */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
          <div style={{ flex: 1, height: "1px", background: "rgba(255, 255, 255, 0.12)" }} />
          <span style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>or with email</span>
          <div style={{ flex: 1, height: "1px", background: "rgba(255, 255, 255, 0.12)" }} />
        </div>

        {/* Standard Email Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {tab === "signup" && (
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#cbd5e1", marginBottom: "6px" }}>
                Full Name
              </label>
              <input
                type="text"
                placeholder="e.g. Tharuksha Sankalpa"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 14px",
                  borderRadius: "8px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  color: "#ffffff",
                  fontSize: "14px",
                  boxSizing: "border-box",
                }}
              />
            </div>
          )}

          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#cbd5e1", marginBottom: "6px" }}>
              Work Email Address
            </label>
            <input
              type="email"
              required
              placeholder="name@organization.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#ffffff",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
              <label style={{ fontSize: "12px", fontWeight: 600, color: "#cbd5e1" }}>Password</label>
              {tab === "signin" && (
                <a href="#forgot" style={{ fontSize: "11px", color: "#60a5fa", textDecoration: "none" }}>
                  Forgot?
                </a>
              )}
            </div>
            <input
              type="password"
              required
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#ffffff",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%", justifyContent: "center", marginTop: "8px", padding: "12px" }}
            disabled={loading}
          >
            {loading ? "Processing..." : tab === "signin" ? "Sign In to Studio" : "Create Free Account"}
          </button>
        </form>

        <p style={{ textAlign: "center", fontSize: "11px", color: "#64748b", marginTop: "18px", margin: "18px 0 0" }}>
          By continuing, you agree to the SLIIT Research J26-DS-334 Data Privacy & Security Protocol.
        </p>
      </div>
    </div>
  );
};
