import React from "react";
import type { TopicTrajectoryPoint } from "../types";

interface Props {
  points: TopicTrajectoryPoint[];
  highlightWeek?: string;
  topicLabel?: string;
  channelName?: string;
}

export const PrevalenceChart: React.FC<Props> = ({ points, highlightWeek, topicLabel, channelName }) => {
  if (!points || points.length === 0) {
    return (
      <div style={{ padding: "40px", textAlign: "center", color: "#64748b" }}>
        No weekly trajectory data available for this selection.
      </div>
    );
  }

  const width = 680;
  const height = 260;
  const padding = { top: 25, right: 30, bottom: 45, left: 50 };

  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // Max prevalence is between 0 and 1
  const maxVal = Math.max(...points.map((p) => p.topic_prevalence), 0.2);

  const getX = (i: number) => padding.left + (points.length > 1 ? (i / (points.length - 1)) * chartW : chartW / 2);
  const getY = (val: number) => padding.top + chartH - (val / maxVal) * chartH;

  // Generate SVG path for prevalence line
  const linePoints = points.map((p, i) => `${getX(i)},${getY(p.topic_prevalence)}`).join(" ");

  // Generate Area under curve
  const areaPoints = `${getX(0)},${padding.top + chartH} ${linePoints} ${getX(points.length - 1)},${padding.top + chartH}`;

  return (
    <div style={{ background: "var(--card-bg, #ffffff)", borderRadius: "10px", padding: "16px", border: "1px solid var(--border-color, #e2e8f0)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
        <div>
          <h4 style={{ margin: 0, fontSize: "15px" }}>Weekly Prevalence Trajectory</h4>
          <span style={{ fontSize: "12px", color: "#64748b" }}>
            {channelName} · {topicLabel}
          </span>
        </div>
        <div style={{ fontSize: "12px", display: "flex", gap: "12px", alignItems: "center" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "10px", height: "10px", background: "#3b82f6", borderRadius: "50%" }} />
            Observed Prevalence
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "12px", height: "4px", background: "#ef4444" }} />
            Changepoint
          </span>
        </div>
      </div>

      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="prevGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Y Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1.0].filter((v) => v <= maxVal * 1.1).map((val) => (
          <g key={val}>
            <line
              x1={padding.left}
              y1={getY(val)}
              x2={width - padding.right}
              y2={getY(val)}
              stroke="#f1f5f9"
              strokeDasharray="4 4"
            />
            <text x={padding.left - 8} y={getY(val) + 4} textAnchor="end" fontSize="10" fill="#94a3b8">
              {Math.round(val * 100)}%
            </text>
          </g>
        ))}

        {/* Area fill */}
        <polygon points={areaPoints} fill="url(#prevGradient)" />

        {/* Line curve */}
        <polyline fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" points={linePoints} />

        {/* Data points and changepoint marker */}
        {points.map((p, i) => {
          const cx = getX(i);
          const cy = getY(p.topic_prevalence);
          const isCp = p.upload_week === highlightWeek;

          return (
            <g key={p.upload_week}>
              {isCp && (
                <>
                  <line
                    x1={cx}
                    y1={padding.top}
                    x2={cx}
                    y2={padding.top + chartH}
                    stroke="#ef4444"
                    strokeWidth="2"
                    strokeDasharray="4 3"
                  />
                  <rect
                    x={cx - 30}
                    y={padding.top - 18}
                    width="60"
                    height="16"
                    rx="4"
                    fill="#ef4444"
                  />
                  <text x={cx} y={padding.top - 6} textAnchor="middle" fontSize="9" fill="#ffffff" fontWeight="bold">
                    CHANGEPOINT
                  </text>
                </>
              )}
              <circle
                cx={cx}
                cy={cy}
                r={isCp ? 6 : 4}
                fill={isCp ? "#ef4444" : "#2563eb"}
                stroke="#ffffff"
                strokeWidth={2}
              />
              {/* X Axis Label */}
              {i % Math.max(1, Math.floor(points.length / 6)) === 0 && (
                <text x={cx} y={padding.top + chartH + 18} textAnchor="middle" fontSize="10" fill="#64748b">
                  {p.upload_week.replace(/^\d{4}-/, "")}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
