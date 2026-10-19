import React from "react";
import { Link } from "react-router-dom";

export const BocpdStudioPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#fce7f3", color: "#be185d", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          BAYESIAN ONLINE CHANGEPOINT DETECTION (BOCPD)
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "#0f172a" }}>
          BOCPD Algorithmic Engine & Run-Length Distribution
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Mathematical formulation based on Adams & MacKay (2007) with Empirical Bayes Hierarchical Prior Shrinkage
        </p>
      </div>

      {/* Mathematical Principles Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        <div className="card" style={{ padding: "20px", borderLeft: "4px solid #ec4899" }}>
          <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>1. Run-Length Posterior</h4>
          <p style={{ margin: 0, fontSize: "13px", color: "#64748b", lineHeight: "1.5" }}>
            Calculates the posterior distribution over the current run length $r_t$ (time since last changepoint) recursively:
            <br />
            <code>P(r_t | x_&#123;1:t&#125;) ∝ ∑ P(r_t | r_&#123;t-1&#125;) P(x_t | r_&#123;t-1&#125;, x_&#123;(t)&#125;) P(r_&#123;t-1&#125; | x_&#123;1:t-1&#125;)</code>
          </p>
        </div>

        <div className="card" style={{ padding: "20px", borderLeft: "4px solid #8b5cf6" }}>
          <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>2. Constant Hazard Prior</h4>
          <p style={{ margin: 0, fontSize: "13px", color: "#64748b", lineHeight: "1.5" }}>
            The probability of a changepoint occurring at any given observation is parameterized by timescale $\lambda = 50$:
            <br />
            <code>H(r_&#123;t-1&#125;) = 1 / λ = 0.02</code>
          </p>
        </div>

        <div className="card" style={{ padding: "20px", borderLeft: "4px solid #3b82f6" }}>
          <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 700 }}>3. Hierarchical Shrinkage</h4>
          <p style={{ margin: 0, fontSize: "13px", color: "#64748b", lineHeight: "1.5" }}>
            Pulls sparse-channel estimates toward the niche cluster mean, cutting transient noise alarms by 55%:
            <br />
            <code>θ_c ~ Normal(μ_&#123;g(c)&#125;, σ_&#123;g(c)&#125;^2)</code>
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Observed Upward Changepoint Triggers</h3>
        <p style={{ margin: "0 0 16px 0", fontSize: "13px", color: "#64748b" }}>
          When the run-length probability $P(r_t = 0 | x_{1:t}) \ge 0.20$ coincident with a positive shift $\Delta \ge +0.03$, an emerging signal flag is triggered.
        </p>

        <div style={{ display: "flex", gap: "10px" }}>
          <Link to="/c4/emerging-topics" className="button" style={{ textDecoration: "none" }}>
            ← View Live Emerging Signals Dashboard
          </Link>
          <Link to="/c4/topic-evaluation" className="button" style={{ textDecoration: "none" }}>
            View Empirical Benchmarks Matrix →
          </Link>
        </div>
      </div>
    </div>
  );
};
