import React from "react";
import type { EmergingTopicSignal } from "../types";

interface Props {
  signal: EmergingTopicSignal;
  isSelected?: boolean;
  onSelect?: (signal: EmergingTopicSignal) => void;
}

const NICHE_COLORS: Record<string, string> = {
  News: "#ef4444",
  Entertainment: "#f59e0b",
  Music: "#8b5cf6",
  Lifestyle: "#06b6d4",
  Culture: "#10b981",
  Education: "#3b82f6",
  Special_Interest: "#ec4899",
  General: "#64748b",
};

export const EmergingSignalCard: React.FC<Props> = ({ signal, isSelected, onSelect }) => {
  const nicheColor = NICHE_COLORS[signal.channel_niche] || "#64748b";
  const probPercent = Math.round(signal.changepoint_probability * 100);

  return (
    <div
      className={`card card--interactive ${isSelected ? "card--selected" : ""}`}
      onClick={() => onSelect?.(signal)}
      style={{
        borderLeft: `4px solid ${nicheColor}`,
        cursor: "pointer",
        transition: "all 0.2s ease-in-out",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
        <div>
          <span
            style={{
              fontSize: "11px",
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: "12px",
              background: `${nicheColor}20`,
              color: nicheColor,
              textTransform: "uppercase",
              letterSpacing: "0.5px",
            }}
          >
            {signal.channel_niche}
          </span>
          <h4 style={{ margin: "6px 0 2px 0", fontSize: "16px", color: "var(--fg-primary, #0f172a)" }}>
            {signal.channel_name}
          </h4>
        </div>
        <div style={{ textAlign: "right" }}>
          <span
            style={{
              fontSize: "11px",
              background: "#dcfce7",
              color: "#15803d",
              padding: "3px 8px",
              borderRadius: "4px",
              fontWeight: 700,
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            📈 Shift +{Math.round(signal.change_magnitude * 100)}%
          </span>
          <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>
            Week: {signal.changepoint_week}
          </div>
        </div>
      </div>

      <div style={{ margin: "10px 0" }}>
        <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--fg-secondary, #334155)" }}>
          {signal.topic_label}
        </div>
      </div>

      {/* Probability Gauge & Credible Interval */}
      <div style={{ background: "var(--bg-subtle, #f8fafc)", padding: "10px", borderRadius: "8px", margin: "10px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
          <span style={{ color: "#64748b" }}>BOCPD Changepoint Prob:</span>
          <strong style={{ color: "var(--accent-color, #2563eb)" }}>{probPercent}%</strong>
        </div>
        <div style={{ width: "100%", height: "6px", background: "#e2e8f0", borderRadius: "3px", overflow: "hidden" }}>
          <div
            style={{
              width: `${probPercent}%`,
              height: "100%",
              background: "linear-gradient(90deg, #3b82f6, #8b5cf6)",
              borderRadius: "3px",
            }}
          />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#64748b", marginTop: "8px" }}>
          <span>Prevalence: <strong>{Math.round(signal.current_prevalence * 100)}%</strong></span>
          <span>95% CI: [{Math.round(signal.ci_lower * 100)}% - {Math.round(signal.ci_upper * 100)}%]</span>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" }}>
        {signal.is_sparse_channel ? (
          <span style={{ fontSize: "11px", color: "#d97706", display: "inline-flex", alignItems: "center", gap: "3px" }}>
            ⚠️ Sparse History (Pooled)
          </span>
        ) : (
          <span style={{ fontSize: "11px", color: "#16a34a" }}>✓ Robust History</span>
        )}
        <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--fg-primary, #0f172a)" }}>
          Signal Score: <span style={{ color: "#2563eb" }}>{signal.signal_score.toFixed(4)}</span>
        </div>
      </div>
    </div>
  );
};
