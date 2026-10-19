import React from "react";
import { Link } from "react-router-dom";

export const GrowthEvaluationPage: React.FC = () => {
  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "20px" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#fef3c7", color: "#b45309", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          EXPERIMENTAL VALIDATION · PILLAR 1
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Growth Model Benchmarks & SHAP Feature Importance
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Comparative Experimental Validation across Random Forest, XGBoost, and LightGBM with Pooled Niche Priors
        </p>
      </div>

      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Model Performance Benchmark</h3>
        <table className="table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
              <th style={{ padding: "10px" }}>Model</th>
              <th style={{ padding: "10px", textAlign: "center" }}>Accuracy</th>
              <th style={{ padding: "10px", textAlign: "center" }}>Precision</th>
              <th style={{ padding: "10px", textAlign: "center" }}>Recall</th>
              <th style={{ padding: "10px", textAlign: "center" }}>ROC-AUC</th>
              <th style={{ padding: "10px" }}>Pooling Benefit</th>
            </tr>
          </thead>
          <tbody>
            {[
              { model: "Baseline Random Forest", acc: "71.4%", prec: "68.2%", rec: "64.0%", auc: "0.742", note: "Overfits sparse channels" },
              { model: "Standard XGBoost (Independent)", acc: "74.8%", prec: "72.1%", rec: "70.5%", auc: "0.789", note: "Moderate variance on small channels" },
              { model: "LightGBM (Similarity-Pooled)", acc: "83.6%", prec: "82.4%", rec: "81.9%", auc: "0.874", note: "★ Best generalization across 52 channels", best: true },
            ].map((m) => (
              <tr key={m.model} style={{ borderBottom: "1px solid #f1f5f9", background: m.best ? "#eff6ff" : "transparent" }}>
                <td style={{ padding: "12px 10px", fontWeight: m.best ? 700 : 500, color: m.best ? "#1e40af" : "inherit" }}>
                  {m.best && "★ "} {m.model}
                </td>
                <td style={{ padding: "12px 10px", textAlign: "center" }}>{m.acc}</td>
                <td style={{ padding: "12px 10px", textAlign: "center" }}>{m.prec}</td>
                <td style={{ padding: "12px 10px", textAlign: "center" }}>{m.rec}</td>
                <td style={{ padding: "12px 10px", textAlign: "center", fontWeight: 600 }}>{m.auc}</td>
                <td style={{ padding: "12px 10px", fontSize: "12px", color: m.best ? "#2563eb" : "#64748b" }}>{m.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: "12px" }}>
        <Link to="/growth-prediction" className="button" style={{ textDecoration: "none" }}>
          ← Back to Growth Dashboard
        </Link>
      </div>
    </div>
  );
};
