import React, { useEffect, useState } from "react";
import { component4Api } from "../api";
import type { EmergingTopicSignal, TopicTrajectoryPoint } from "../types";
import { EmergingSignalCard } from "../components/EmergingSignalCard";
import { PrevalenceChart } from "../components/PrevalenceChart";

const NICHES = ["All", "News", "Music", "Entertainment", "Lifestyle", "Culture", "Education"];

export const EmergingTopicsPage: React.FC = () => {
  const [signals, setSignals] = useState<EmergingTopicSignal[]>([]);
  const [selectedSignal, setSelectedSignal] = useState<EmergingTopicSignal | null>(null);
  const [trajectories, setTrajectories] = useState<TopicTrajectoryPoint[]>([]);
  const [selectedNiche, setSelectedNiche] = useState<string>("All");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    component4Api
      .getEmergingTopics({ niche: selectedNiche })
      .then((data) => {
        setSignals(data);
        if (data.length > 0 && !selectedSignal) {
          setSelectedSignal(data[0]);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load emerging topic signals");
        setLoading(false);
      });
  }, [selectedNiche]);

  useEffect(() => {
    if (selectedSignal) {
      component4Api
        .getTrajectories({ channelId: selectedSignal.channel_id, topicId: selectedSignal.topic_id })
        .then((data) => setTrajectories(data))
        .catch(() => setTrajectories([]));
    }
  }, [selectedSignal]);

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "20px" }}>
      {/* Page Header */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "inline-block", padding: "4px 10px", background: "#e0f2fe", color: "#0369a1", borderRadius: "16px", fontSize: "12px", fontWeight: 700, marginBottom: "8px" }}>
          RESEARCH COMPONENT 4
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Emerging Topic Intelligence
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Hierarchically Pooled Dynamic Topic Modelling with Bayesian Online Changepoint Detection (BOCPD)
        </p>
      </div>

      {/* KPI Stats Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #3b82f6" }}>
          <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>Analyzed Videos</div>
          <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", marginTop: "4px" }}>1,682</div>
          <div style={{ fontSize: "11px", color: "#16a34a", marginTop: "4px" }}>Across 52 portfolio channels</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #8b5cf6" }}>
          <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>Discovered Topics</div>
          <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", marginTop: "4px" }}>15 Topics</div>
          <div style={{ fontSize: "11px", color: "#8b5cf6", marginTop: "4px" }}>Diversity Metric: 90.7%</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #10b981" }}>
          <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>Emerging Signals</div>
          <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", marginTop: "4px" }}>{signals.length} Signals</div>
          <div style={{ fontSize: "11px", color: "#10b981", marginTop: "4px" }}>Probabilistic Upward Momentum</div>
        </div>

        <div className="card" style={{ padding: "16px", borderLeft: "4px solid #f59e0b" }}>
          <div style={{ fontSize: "12px", color: "#64748b", textTransform: "uppercase" }}>False Alarm Rate</div>
          <div style={{ fontSize: "24px", fontWeight: 800, color: "#0f172a", marginTop: "4px" }}>20.0%</div>
          <div style={{ fontSize: "11px", color: "#16a34a", marginTop: "4px" }}>Reduced from 44.8% (CUSUM)</div>
        </div>
      </div>

      {/* Filter Bar */}
      <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "12px", marginBottom: "20px" }}>
        {NICHES.map((niche) => (
          <button
            key={niche}
            className={`btn ${selectedNiche === niche ? "btn--primary" : "btn--secondary"}`}
            onClick={() => setSelectedNiche(niche)}
            style={{
              padding: "6px 14px",
              borderRadius: "20px",
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            {niche}
          </button>
        ))}
      </div>

      {/* Main Split Layout: Cards on Left, Visualizer on Right */}
      {loading ? (
        <div style={{ padding: "60px", textAlign: "center", color: "#64748b" }}>Loading detected emerging signals...</div>
      ) : error ? (
        <div style={{ padding: "40px", color: "#ef4444", background: "#fef2f2", borderRadius: "8px" }}>{error}</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: "24px", alignItems: "flex-start" }}>
          {/* Signal Cards List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <h3 style={{ margin: 0, fontSize: "16px" }}>
              Ranked Emerging Topic Flags ({signals.length})
            </h3>
            {signals.length === 0 ? (
              <div style={{ padding: "30px", textAlign: "center", color: "#64748b", background: "#f8fafc", borderRadius: "8px" }}>
                No emerging signals detected in this niche filter.
              </div>
            ) : (
              signals.map((s) => (
                <EmergingSignalCard
                  key={`${s.channel_id}-${s.topic_id}-${s.changepoint_week}`}
                  signal={s}
                  isSelected={selectedSignal?.channel_id === s.channel_id && selectedSignal?.topic_id === s.topic_id}
                  onSelect={(sig) => setSelectedSignal(sig)}
                />
              ))
            )}
          </div>

          {/* Detailed Trajectory & Decision Visualizer */}
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            {selectedSignal ? (
              <>
                <PrevalenceChart
                  points={trajectories}
                  highlightWeek={selectedSignal.changepoint_week}
                  topicLabel={selectedSignal.topic_label}
                  channelName={selectedSignal.channel_name}
                />

                {/* Manager Decision Commissioning Card */}
                <div className="card" style={{ padding: "20px", background: "linear-gradient(135deg, #f8fafc, #eff6ff)" }}>
                  <h4 style={{ margin: "0 0 8px 0", fontSize: "15px", color: "#1e40af" }}>
                    🎯 Decision Support & Recommendation
                  </h4>
                  <p style={{ fontSize: "13px", color: "#334155", lineHeight: "1.6", margin: "0 0 12px 0" }}>
                    <strong>{selectedSignal.channel_name}</strong> shows a verified upward changepoint in{" "}
                    <strong>{selectedSignal.topic_label}</strong> with <strong>{Math.round(selectedSignal.changepoint_probability * 100)}%</strong> posterior probability and a{" "}
                    <strong>+{Math.round(selectedSignal.change_magnitude * 100)}%</strong> shift in weekly prevalence.
                  </p>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", background: "#ffffff", padding: "12px", borderRadius: "6px", fontSize: "12px" }}>
                    <div>
                      <span style={{ color: "#64748b" }}>Prevalence Estimate:</span>
                      <div style={{ fontWeight: 700, fontSize: "14px", color: "#0f172a" }}>
                        {Math.round(selectedSignal.current_prevalence * 100)}%
                      </div>
                    </div>
                    <div>
                      <span style={{ color: "#64748b" }}>95% Bayesian Uncertainty:</span>
                      <div style={{ fontWeight: 700, fontSize: "14px", color: "#2563eb" }}>
                        [{Math.round(selectedSignal.ci_lower * 100)}% - {Math.round(selectedSignal.ci_upper * 100)}%]
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div style={{ padding: "60px", textAlign: "center", color: "#64748b" }}>
                Select an emerging topic card to visualize its weekly trajectory.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
