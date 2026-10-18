import React from "react";
import type { BenchmarkResult } from "../types";

interface Props {
  benchmarks: BenchmarkResult[];
}

export const BenchmarkMatrix: React.FC<Props> = ({ benchmarks }) => {
  return (
    <div className="card" style={{ padding: "20px" }}>
      <div style={{ marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "18px" }}>Methodological Benchmark Comparison</h3>
        <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "#64748b" }}>
          Empirical evaluation across all 52 media organization channels comparing proposed Hierarchical BOCPD against baseline methods.
        </p>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
              <th style={{ padding: "10px" }}>Methodology</th>
              <th style={{ padding: "10px", textAlign: "center" }}>Detected Flags</th>
              <th style={{ padding: "10px", textAlign: "center" }}>Transient Spikes</th>
              <th style={{ padding: "10px" }}>False Alarm Rate (%)</th>
              <th style={{ padding: "10px" }}>Prevalence Stability</th>
              <th style={{ padding: "10px" }}>Uncertainty Aware</th>
            </tr>
          </thead>
          <tbody>
            {benchmarks.map((b) => {
              const isProposed = b.Methodology.includes("Proposed");
              const fa = b["False Alarm Rate (%)"];
              const stab = b["Prevalence Stability Score"];

              return (
                <tr
                  key={b.Methodology}
                  style={{
                    borderBottom: "1px solid #f1f5f9",
                    background: isProposed ? "#eff6ff" : "transparent",
                    fontWeight: isProposed ? 600 : 400,
                  }}
                >
                  <td style={{ padding: "12px 10px", display: "flex", alignItems: "center", gap: "8px" }}>
                    {isProposed && <span style={{ color: "#2563eb", fontSize: "16px" }}>★</span>}
                    <strong style={{ color: isProposed ? "#1e40af" : "inherit" }}>{b.Methodology}</strong>
                  </td>
                  <td style={{ padding: "12px 10px", textAlign: "center" }}>{b["Detected Emerging Flags"]}</td>
                  <td style={{ padding: "12px 10px", textAlign: "center", color: b["Transient / Noise Spikes"] > 5 ? "#ef4444" : "inherit" }}>
                    {b["Transient / Noise Spikes"]}
                  </td>
                  <td style={{ padding: "12px 10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ minWidth: "45px", color: fa < 25 ? "#16a34a" : "#dc2626" }}>
                        {fa.toFixed(1)}%
                      </span>
                      <div style={{ width: "80px", height: "6px", background: "#e2e8f0", borderRadius: "3px" }}>
                        <div
                          style={{
                            width: `${Math.min(100, fa * 2)}%`,
                            height: "100%",
                            background: fa < 25 ? "#22c55e" : "#ef4444",
                            borderRadius: "3px",
                          }}
                        />
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "12px 10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ minWidth: "35px", color: stab >= 0.75 ? "#16a34a" : "#d97706" }}>
                        {stab.toFixed(3)}
                      </span>
                      <div style={{ width: "80px", height: "6px", background: "#e2e8f0", borderRadius: "3px" }}>
                        <div
                          style={{
                            width: `${Math.min(100, stab * 100)}%`,
                            height: "100%",
                            background: stab >= 0.75 ? "#3b82f6" : "#f59e0b",
                            borderRadius: "3px",
                          }}
                        />
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "12px 10px" }}>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: "12px",
                        fontSize: "11px",
                        background: isProposed ? "#dbeafe" : "#f1f5f9",
                        color: isProposed ? "#1d4ed8" : "#64748b",
                        fontWeight: 600,
                      }}
                    >
                      {b["Provides Uncertainty"]}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
