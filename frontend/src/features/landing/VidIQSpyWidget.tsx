import React, { useState } from "react";
import { Link } from "react-router-dom";

interface ChannelData {
  id: string;
  name: string;
  niche: string;
  subscribers: string;
  viewsPerSub: number;
  growthScore: number;
  demandIntensity: string;
  emergingTopic: string;
  changepointStatus: string;
  bridgeRecommendation: string;
  flag: "Underperforming" | "Flagship" | "Breakout" | "Growth Opportunity";
}

const SAMPLE_PORTFOLIO: ChannelData[] = [
  {
    id: "UCHKtXGbqRIM0hA4Manb9DNg",
    name: "TV Derana",
    niche: "Entertainment",
    subscribers: "5.1M",
    viewsPerSub: 0.48,
    growthScore: 88,
    demandIntensity: "High (38% Content Requests)",
    emergingTopic: "Mega Teledrama & Reality",
    changepointStatus: "Stable Plateau",
    bridgeRecommendation: "Acts as Primary Bridge Provider",
    flag: "Flagship",
  },
  {
    id: "UCJr5vlnK6HEBVISUtxnq_sg",
    name: "eTunes",
    niche: "Music & Acoustic",
    subscribers: "120K",
    viewsPerSub: 0.14,
    growthScore: 42,
    demandIntensity: "Very High (45% Acoustic Requests)",
    emergingTopic: "Sinhala Acoustic Unplugged",
    changepointStatus: "Structural Upward Shift Detected (BOCPD)",
    bridgeRecommendation: "Bridge from TV Derana & City Of Music",
    flag: "Underperforming",
  },
  {
    id: "UC3_v6xKq_Ua2r6M7",
    name: "Lokaya Saha Lokayo",
    niche: "Entertainment / Investigative",
    subscribers: "290K",
    viewsPerSub: 0.19,
    growthScore: 56,
    demandIntensity: "Extreme (52% Investigative Gap)",
    emergingTopic: "Exclusive Documentaries",
    changepointStatus: "Upward Changepoint Confirmed (Week 43)",
    bridgeRecommendation: "Bridge from Ada Derana 24",
    flag: "Growth Opportunity",
  },
  {
    id: "UC7_v8xKq_Ua2r6M8",
    name: "FM Derana",
    niche: "News & Radio Talk",
    subscribers: "340K",
    viewsPerSub: 0.28,
    growthScore: 74,
    demandIntensity: "Moderate (22% Requests)",
    emergingTopic: "Morning Show Highlights",
    changepointStatus: "Probabilistic Shift: 65%",
    bridgeRecommendation: "Bridge to Music Channels",
    flag: "Breakout",
  },
  {
    id: "UC9_v0xKq_Ua2r6M9",
    name: "Derana City Of Music",
    niche: "Music & Live Concerts",
    subscribers: "480K",
    viewsPerSub: 0.22,
    growthScore: 65,
    demandIntensity: "High (34% Live Audio Requests)",
    emergingTopic: "Unplugged Sessions",
    changepointStatus: "Moderate Upward Momentum",
    bridgeRecommendation: "Cross-promote with eTunes",
    flag: "Growth Opportunity",
  },
];

export const VidIQSpyWidget: React.FC = () => {
  const [selectedChannel, setSelectedChannel] = useState<ChannelData>(SAMPLE_PORTFOLIO[1]); // default eTunes

  return (
    <div className="vidiq-inspector">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "24px", flexWrap: "wrap", gap: "16px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <span style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", borderRadius: "6px", background: "rgba(59, 130, 246, 0.2)", color: "#60a5fa" }}>
              LIVE NETWORK INSPECTOR
            </span>
            <span style={{ fontSize: "12px", color: "#94a3b8" }}>52 Monitored Media Organization Channels</span>
          </div>
          <h3 style={{ fontSize: "22px", fontWeight: 800, margin: 0, color: "#ffffff" }}>
            Channel & Topic Intelligence Diagnostic Engine
          </h3>
        </div>

        {/* Channel Selector Pills */}
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {SAMPLE_PORTFOLIO.map((ch) => (
            <button
              key={ch.id}
              type="button"
              onClick={() => setSelectedChannel(ch)}
              style={{
                background: selectedChannel.id === ch.id ? "var(--brand-gradient)" : "rgba(255, 255, 255, 0.06)",
                color: "#ffffff",
                border: selectedChannel.id === ch.id ? "none" : "1px solid rgba(255, 255, 255, 0.12)",
                padding: "8px 14px",
                borderRadius: "8px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {ch.name}
            </button>
          ))}
        </div>
      </div>

      {/* Main Diagnostic Panel */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "16px",
          background: "rgba(15, 23, 42, 0.6)",
          padding: "20px",
          borderRadius: "14px",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          marginBottom: "24px",
        }}
      >
        <div>
          <div style={{ fontSize: "11px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Channel Niche</div>
          <div style={{ fontSize: "18px", fontWeight: 700, color: "#ffffff", marginTop: "4px" }}>{selectedChannel.niche}</div>
          <div style={{ fontSize: "12px", color: "#60a5fa", marginTop: "2px" }}>{selectedChannel.subscribers} Subscribers</div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Opportunity Score</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px", marginTop: "4px" }}>
            <span
              style={{
                fontSize: "26px",
                fontWeight: 900,
                color: selectedChannel.growthScore >= 70 ? "#34d399" : selectedChannel.growthScore >= 50 ? "#fbbf24" : "#f87171",
              }}
            >
              {selectedChannel.growthScore}
            </span>
            <span style={{ fontSize: "13px", color: "#94a3b8" }}>/ 100</span>
          </div>
          <div style={{ fontSize: "11px", color: "#94a3b8" }}>Pillar 1 Pooled ML Model</div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>BOCPD Topic Momentum</div>
          <div style={{ fontSize: "15px", fontWeight: 700, color: "#f472b6", marginTop: "4px" }}>
            {selectedChannel.emergingTopic}
          </div>
          <div style={{ fontSize: "11px", color: "#34d399", marginTop: "2px" }}>{selectedChannel.changepointStatus}</div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Audience Bridge Transfer</div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#a78bfa", marginTop: "4px" }}>
            {selectedChannel.bridgeRecommendation}
          </div>
          <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>Pillar 3 PageRank Diffusion</div>
        </div>
      </div>

      {/* Action Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              padding: "4px 10px",
              borderRadius: "12px",
              fontSize: "12px",
              fontWeight: 700,
              background:
                selectedChannel.flag === "Underperforming"
                  ? "rgba(239, 68, 68, 0.2)"
                  : selectedChannel.flag === "Flagship"
                  ? "rgba(59, 130, 246, 0.2)"
                  : "rgba(16, 185, 129, 0.2)",
              color:
                selectedChannel.flag === "Underperforming"
                  ? "#fca5a5"
                  : selectedChannel.flag === "Flagship"
                  ? "#93c5fd"
                  : "#6ee7b7",
            }}
          >
            STATUS: {selectedChannel.flag.toUpperCase()}
          </span>
          <span style={{ fontSize: "13px", color: "#cbd5e1" }}>
            Diagnosis: <strong>{selectedChannel.viewsPerSub}</strong> views per subscriber ratio
          </span>
        </div>

        <div style={{ display: "flex", gap: "10px" }}>
          <Link
            to="/c4/emerging-topics"
            className="btn-primary"
            style={{ fontSize: "13px", padding: "8px 16px" }}
          >
            Inspect Topic Trajectory (Pillar 4) →
          </Link>
          <Link
            to="/c3/audience-bridges"
            className="btn-secondary"
            style={{ fontSize: "13px", padding: "8px 16px" }}
          >
            View Bridge Graph (Pillar 3)
          </Link>
        </div>
      </div>
    </div>
  );
};
