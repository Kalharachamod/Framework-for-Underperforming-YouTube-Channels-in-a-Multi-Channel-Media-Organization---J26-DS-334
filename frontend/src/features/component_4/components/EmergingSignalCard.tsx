import React, { useState } from "react";
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
  const [showAiIdeas, setShowAiIdeas] = useState<boolean>(false);
  const nicheColor = NICHE_COLORS[signal.channel_niche] || "#64748b";
  const probPercent = Math.round(signal.changepoint_probability * 100);

  // Lifecycle Stage Calculation based on BOCPD changepoint probability and magnitude
  const isEarlyEmergence = probPercent >= 70;
  const stageBadge = isEarlyEmergence
    ? { text: "🟢 Early Emergence", color: "#15803d", bg: "#dcfce7", window: "~3.5 wks before peak saturation" }
    : { text: "🟡 Mainstream Surge", color: "#b45309", bg: "#fef3c7", window: "~1.5 wks before plateau" };

  // Generated Video Concepts (Bilingual)
  const videoConcepts = [
    {
      titleFormula: `[Artist / Topic] - Unplugged Exclusive | ${signal.channel_name} Studio`,
      hook: "Open with a 5-second acoustic guitar hook before revealing the guest artist.",
      tags: ["#AcousticCover", "#SinhalaSongs", "#LiveSession", "#TrendoraExclusive"],
    },
    {
      titleFormula: `නොඇසූ කතාව: The Story Behind ${signal.topic_label.slice(0, 24)}...`,
      hook: "Behind-the-scenes rehearsal footage with raw audio stem breakdown.",
      tags: ["#SinhalaMusic", "#StudioVlog", "#TrendingSriLanka"],
    },
  ];

  return (
    <div
      className={`card card--interactive ${isSelected ? "card--selected" : ""}`}
      style={{
        borderLeft: `4px solid ${nicheColor}`,
        transition: "all 0.2s ease-in-out",
        padding: "16px",
        marginBottom: "12px",
      }}
    >
      {/* Card Header */}
      <div
        onClick={() => onSelect?.(signal)}
        style={{ cursor: "pointer" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <div>
            <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
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
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 700,
                  padding: "2px 6px",
                  borderRadius: "8px",
                  background: stageBadge.bg,
                  color: stageBadge.color,
                }}
              >
                {stageBadge.text}
              </span>
            </div>
            <h4 style={{ margin: "6px 0 2px 0", fontSize: "16px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
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
              Week {signal.changepoint_week}
            </div>
          </div>
        </div>

        {/* Topic Label */}
        <div style={{ margin: "10px 0" }}>
          <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--fg-secondary, #334155)" }}>
            {signal.topic_label}
          </div>
          <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>
            Window: <strong>{stageBadge.window}</strong>
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
                background: "linear-gradient(90deg, #3b82f6, #ec4899)",
                borderRadius: "3px",
              }}
            />
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#64748b", marginTop: "8px" }}>
            <span>Prevalence: <strong>{Math.round(signal.current_prevalence * 100)}%</strong></span>
            <span>95% CI: [{Math.round(signal.ci_lower * 100)}% - {Math.round(signal.ci_upper * 100)}%]</span>
          </div>
        </div>

        {/* Signal Score & Sparsity */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" }}>
          {signal.is_sparse_channel ? (
            <span style={{ fontSize: "11px", color: "#d97706", display: "inline-flex", alignItems: "center", gap: "3px" }}>
              ⚠️ Sparse Channel (Empirical Prior Pooled)
            </span>
          ) : (
            <span style={{ fontSize: "11px", color: "#16a34a" }}>✓ Robust Channel History</span>
          )}
          <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--fg-primary, #0f172a)" }}>
            Signal Score: <span style={{ color: "#2563eb" }}>{signal.signal_score.toFixed(4)}</span>
          </div>
        </div>
      </div>

      {/* AI Concept Generator Toggle Button */}
      <div style={{ marginTop: "12px", borderTop: "1px solid #f1f5f9", paddingTop: "10px" }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowAiIdeas(!showAiIdeas);
          }}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px",
            padding: "8px 12px",
            borderRadius: "6px",
            border: "1px solid #e0e7ff",
            background: showAiIdeas ? "#eef2ff" : "#f8fafc",
            color: "#4f46e5",
            fontSize: "12px",
            fontWeight: 700,
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
        >
          <span>✨</span>
          <span>{showAiIdeas ? "Hide AI Video Concepts" : "Generate Video Concepts & Titles"}</span>
        </button>

        {/* Expandable AI Concept Ideas */}
        {showAiIdeas && (
          <div
            style={{
              marginTop: "10px",
              background: "#ffffff",
              borderRadius: "8px",
              padding: "12px",
              border: "1px solid #c7d2fe",
              boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.05)",
            }}
          >
            <div style={{ fontSize: "11px", fontWeight: 800, color: "#4338ca", textTransform: "uppercase", marginBottom: "8px" }}>
              High-CTR Packaging Concepts for {signal.channel_name}:
            </div>

            {videoConcepts.map((c, idx) => (
              <div
                key={idx}
                style={{
                  background: "#f8fafc",
                  borderRadius: "6px",
                  padding: "8px 10px",
                  marginBottom: "8px",
                  borderLeft: "3px solid #6366f1",
                }}
              >
                <div style={{ fontSize: "12px", fontWeight: 700, color: "#0f172a" }}>
                  Idea #{idx + 1}: {c.titleFormula}
                </div>
                <div style={{ fontSize: "11px", color: "#64748b", margin: "3px 0" }}>
                  💡 <strong>Hook:</strong> {c.hook}
                </div>
                <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px" }}>
                  {c.tags.map((t) => (
                    <span
                      key={t}
                      style={{
                        fontSize: "10px",
                        padding: "1px 6px",
                        borderRadius: "4px",
                        background: "#eef2ff",
                        color: "#4f46e5",
                      }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
