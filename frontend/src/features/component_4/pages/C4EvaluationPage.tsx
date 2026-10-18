import React, { useEffect, useState } from "react";
import { component4Api } from "../api";
import type { BenchmarkResult } from "../types";
import { BenchmarkMatrix } from "../components/BenchmarkMatrix";

export const C4EvaluationPage: React.FC = () => {
  const [benchmarks, setBenchmarks] = useState<BenchmarkResult[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    component4Api
      .getBenchmarks()
      .then((data) => {
        setBenchmarks(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load benchmark evaluation");
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "20px" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#fef3c7", color: "#b45309", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          EXPERIMENTAL VALIDATION
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Emerging Topic Benchmark & Evaluation
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Comparative Experimental Validation across Heuristic, Statistical, and Hierarchical Bayesian Methods
        </p>
      </div>

      {loading ? (
        <div style={{ padding: "60px", textAlign: "center", color: "#64748b" }}>Loading benchmark results...</div>
      ) : error ? (
        <div style={{ padding: "40px", color: "#ef4444", background: "#fef2f2", borderRadius: "8px" }}>{error}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <BenchmarkMatrix benchmarks={benchmarks} />

          {/* Research Insights & Findings */}
          <div className="card" style={{ padding: "24px", background: "var(--card-bg, #ffffff)" }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "17px" }}>🔬 Key Empirical Findings</h3>
            <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "14px", lineHeight: "1.8", color: "#334155" }}>
              <li>
                <strong>Heuristic Trend Vulnerability:</strong> Standard Moving-Average and CUSUM change detection suffer from false alarm rates of <strong>42.9% - 44.8%</strong>, because temporary single-video uploads in sparse channels masquerade as sudden topic growth.
              </li>
              <li>
                <strong>Hierarchical Shrinkage Effect:</strong> Bayesian partial pooling across niche-similar channels pulls sparse channel estimates toward the robust group prior, cutting the false alarm rate to <strong>20.0%</strong> (more than halved).
              </li>
              <li>
                <strong>Prevalence Stability:</strong> Stability score increased from <strong>0.552 to 0.800</strong>, preventing volatile decision swings for media managers.
              </li>
              <li>
                <strong>Uncertainty Calibration:</strong> Unlike heuristic tools (which provide bare point estimates), the proposed framework equips managers with <strong>95% Credible Intervals</strong> for risk-managed programming.
              </li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};
