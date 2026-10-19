import React, { useState, useEffect, useRef } from "react";

interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: string;
  structuredCard?: {
    title: string;
    status: string;
    executiveSummary: string;
    gap: string;
    emergingTopic: string;
    bridgePartner: string;
    actionPlan: Array<{ day: string; phase: string; action: string; pillar: string }>;
  };
}

const PRESET_CHANNELS = [
  { id: "eTunes", name: "eTunes", niche: "Music", subs: "120K", vps: 0.14, status: "Underperforming Target" },
  { id: "Lokaya Saha Lokayo", name: "Lokaya Saha Lokayo", niche: "Entertainment", subs: "290K", vps: 0.19, status: "Underperforming Target" },
  { id: "TV Derana", name: "TV Derana", niche: "Entertainment", subs: "6.6M", vps: 1.66, status: "Flagship / Stable" },
  { id: "Ada Derana 24", name: "Ada Derana 24", niche: "News", subs: "1.8M", vps: 0.62, status: "High Momentum" },
  { id: "Derana City Of Music", name: "Derana City Of Music", niche: "Music", subs: "480K", vps: 0.22, status: "Moderate Opportunity" },
  { id: "DAM DERANA", name: "DAM DERANA", niche: "Culture", subs: "95K", vps: 0.11, status: "Underperforming Target" },
];

export const TrendoraAIChatbot: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState(PRESET_CHANNELS[0]);
  const [inputMessage, setInputMessage] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [ollamaStatus, setOllamaStatus] = useState<{ online: boolean; model: string; message: string }>({
    online: false,
    model: "trendora-research-engine",
    message: "Connecting...",
  });

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "bot",
      text: "👋 Hi! I'm **Trendora AI Copilot**, your multi-channel growth advisor powered by SLIIT CoEAI research (J26-DS-334).\n\nSelect a channel and ask me anything, or tap a quick action below to diagnose performance and generate action plans!",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Check local Ollama status
    fetch("http://127.0.0.1:8000/api/v1/ai/status")
      .then((res) => res.json())
      .then((data) => {
        setOllamaStatus({
          online: data.online,
          model: data.active_model || "trendora-research-engine",
          message: data.message,
        });
      })
      .catch(() => {
        setOllamaStatus({
          online: false,
          model: "trendora-research-engine",
          message: "Research deterministic synthesis mode active",
        });
      });
  }, []);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen, isTyping]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputMessage("");
    setIsTyping(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/v1/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          channel_context: selectedChannel.name,
        }),
      });

      if (!res.ok) throw new Error("Chat request failed");
      const data = await res.json();

      const botMsg: ChatMessage = {
        id: `b-${Date.now()}`,
        sender: "bot",
        text: data.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      const botFallback: ChatMessage = {
        id: `b-${Date.now()}`,
        sender: "bot",
        text: `Based on **${selectedChannel.name}** (${selectedChannel.niche}), our 4-pillar intelligence framework recommends prioritizing the emerging topic detected by BOCPD and establishing a cross-channel promotion link with flagship channels to improve velocity.`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, botFallback]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleGeneratePlaybook = async () => {
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: `🚀 Generate complete 14-day growth playbook for ${selectedChannel.name}`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/v1/ai/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_name: selectedChannel.name,
          niche: selectedChannel.niche,
          subs: selectedChannel.subs,
          views_per_sub: selectedChannel.vps,
        }),
      });

      if (!res.ok) throw new Error("Playbook request failed");
      const data = await res.json();

      const botMsg: ChatMessage = {
        id: `b-${Date.now()}`,
        sender: "bot",
        text: `Here is the comprehensive 4-Pillar Growth Playbook for **${selectedChannel.name}**:`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        structuredCard: {
          title: `Growth Strategy: ${data.channel_name}`,
          status: data.pillar_1_diagnostic.status,
          executiveSummary: data.executive_summary,
          gap: data.pillar_1_diagnostic.gap,
          emergingTopic: data.pillar_4_bocpd_topics.emerging_topic,
          bridgePartner: `${data.pillar_3_bridges.primary_bridge_channel} (Affinity: ${data.pillar_3_bridges.bridge_affinity_score})`,
          actionPlan: data.action_plan_14_days,
        },
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      handleSendMessage(`Provide a growth recommendation for ${selectedChannel.name}`);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <>
      {/* Floating Launcher Button */}
      <div
        style={{
          position: "fixed",
          bottom: "24px",
          right: "24px",
          zIndex: 9999,
        }}
      >
        {!isOpen && (
          <button
            onClick={() => setIsOpen(true)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "12px 20px",
              borderRadius: "50px",
              border: "none",
              background: "linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%)",
              color: "#ffffff",
              fontSize: "14px",
              fontWeight: 700,
              cursor: "pointer",
              boxShadow: "0 10px 25px -3px rgba(99, 102, 241, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.1)",
              transition: "transform 0.2s ease, box-shadow 0.2s ease",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.transform = "translateY(-3px)")}
            onMouseLeave={(e) => (e.currentTarget.style.transform = "translateY(0)")}
          >
            <span style={{ fontSize: "18px" }}>✨</span>
            <span>Trendora AI Copilot</span>
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: ollamaStatus.online ? "#4ade80" : "#38bdf8",
                boxShadow: `0 0 8px ${ollamaStatus.online ? "#4ade80" : "#38bdf8"}`,
              }}
            />
          </button>
        )}
      </div>

      {/* Floating Glassmorphic Chat Window */}
      {isOpen && (
        <div
          style={{
            position: "fixed",
            bottom: "24px",
            right: "24px",
            width: "420px",
            maxWidth: "calc(100vw - 32px)",
            height: "620px",
            maxHeight: "calc(100vh - 48px)",
            background: "#ffffff",
            borderRadius: "20px",
            boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.35), 0 0 0 1px rgba(15, 23, 42, 0.08)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            zIndex: 9999,
            animation: "fadeIn 0.25s ease-out",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "16px 18px",
              background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)",
              color: "#ffffff",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "10px",
                  background: "linear-gradient(135deg, #6366f1, #ec4899)",
                  display: "grid",
                  placeItems: "center",
                  fontSize: "18px",
                }}
              >
                ✨
              </div>
              <div>
                <div style={{ fontSize: "14px", fontWeight: 800, display: "flex", alignItems: "center", gap: "6px" }}>
                  Trendora AI Copilot
                </div>
                <div style={{ fontSize: "11px", color: "#94a3b8", display: "flex", alignItems: "center", gap: "6px" }}>
                  <span
                    style={{
                      width: "6px",
                      height: "6px",
                      borderRadius: "50%",
                      background: ollamaStatus.online ? "#4ade80" : "#38bdf8",
                    }}
                  />
                  {ollamaStatus.online ? `Ollama (${ollamaStatus.model})` : "Research Synthesis Engine"}
                </div>
              </div>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              style={{
                background: "rgba(255, 255, 255, 0.1)",
                border: "none",
                color: "#94a3b8",
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                cursor: "pointer",
                display: "grid",
                placeItems: "center",
                fontSize: "16px",
              }}
            >
              ✕
            </button>
          </div>

          {/* Active Channel Selector Bar */}
          <div
            style={{
              padding: "10px 14px",
              background: "#f8fafc",
              borderBottom: "1px solid #e2e8f0",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>
              Active Channel:
            </span>
            <select
              value={selectedChannel.name}
              onChange={(e) => {
                const found = PRESET_CHANNELS.find((c) => c.name === e.target.value);
                if (found) setSelectedChannel(found);
              }}
              style={{
                fontSize: "12px",
                fontWeight: 700,
                padding: "4px 8px",
                borderRadius: "6px",
                border: "1px solid #cbd5e1",
                background: "#ffffff",
                color: "#0f172a",
                cursor: "pointer",
              }}
            >
              {PRESET_CHANNELS.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.niche} · {c.subs})
                </option>
              ))}
            </select>
          </div>

          {/* Messages Stream */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px",
              display: "flex",
              flexDirection: "column",
              gap: "14px",
              background: "#fdfdfd",
            }}
          >
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: m.sender === "user" ? "flex-end" : "flex-start",
                }}
              >
                <div
                  style={{
                    maxWidth: "88%",
                    padding: "12px 14px",
                    borderRadius: m.sender === "user" ? "14px 14px 2px 14px" : "14px 14px 14px 2px",
                    background: m.sender === "user" ? "#2563eb" : "#f1f5f9",
                    color: m.sender === "user" ? "#ffffff" : "#1e293b",
                    fontSize: "13px",
                    lineHeight: "1.5",
                    boxShadow: m.sender === "user" ? "0 2px 6px rgba(37, 99, 235, 0.25)" : "none",
                  }}
                >
                  <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>

                  {/* Render Structured Growth Strategy Card if available */}
                  {m.structuredCard && (
                    <div
                      style={{
                        marginTop: "12px",
                        background: "#ffffff",
                        borderRadius: "10px",
                        padding: "12px",
                        border: "1px solid #cbd5e1",
                        color: "#0f172a",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                        <span style={{ fontSize: "12px", fontWeight: 800, color: "#1e1b4b" }}>
                          {m.structuredCard.title}
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "10px",
                            background: "#fee2e2",
                            color: "#b91c1c",
                          }}
                        >
                          {m.structuredCard.status}
                        </span>
                      </div>

                      <p style={{ fontSize: "11px", color: "#475569", margin: "0 0 10px 0" }}>
                        {m.structuredCard.executiveSummary}
                      </p>

                      <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "11px", marginBottom: "10px" }}>
                        <div>
                          <strong>Deficit:</strong> <span style={{ color: "#dc2626" }}>{m.structuredCard.gap}</span>
                        </div>
                        <div>
                          <strong>Emerging Topic (C4):</strong>{" "}
                          <span style={{ color: "#0369a1", fontWeight: 600 }}>{m.structuredCard.emergingTopic}</span>
                        </div>
                        <div>
                          <strong>Bridge Partner (C3):</strong>{" "}
                          <span style={{ color: "#7c3aed", fontWeight: 600 }}>{m.structuredCard.bridgePartner}</span>
                        </div>
                      </div>

                      <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: "8px" }}>
                        <div style={{ fontSize: "10px", fontWeight: 800, textTransform: "uppercase", color: "#64748b", marginBottom: "4px" }}>
                          14-Day Action Roadmap:
                        </div>
                        {m.structuredCard.actionPlan.map((step) => (
                          <div key={step.day} style={{ fontSize: "11px", marginBottom: "4px" }}>
                            <span style={{ fontWeight: 700, color: "#2563eb" }}>{step.day}:</span> {step.action}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <span style={{ fontSize: "10px", color: "#94a3b8", marginTop: "3px", padding: "0 4px" }}>
                  {m.timestamp}
                </span>
              </div>
            ))}

            {isTyping && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", padding: "8px 12px", background: "#f1f5f9", borderRadius: "12px", width: "fit-content" }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#6366f1", animation: "bounce 1s infinite 0.1s" }} />
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#a855f7", animation: "bounce 1s infinite 0.2s" }} />
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#ec4899", animation: "bounce 1s infinite 0.3s" }} />
                <span style={{ fontSize: "11px", color: "#64748b", marginLeft: "4px" }}>Synthesizing 4-pillar data...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Action Suggestion Chips */}
          <div
            style={{
              padding: "8px 14px",
              background: "#ffffff",
              borderTop: "1px solid #f1f5f9",
              display: "flex",
              gap: "6px",
              overflowX: "auto",
              whiteSpace: "nowrap",
            }}
          >
            <button
              onClick={handleGeneratePlaybook}
              disabled={isTyping}
              style={{
                fontSize: "11px",
                fontWeight: 600,
                padding: "5px 10px",
                borderRadius: "16px",
                border: "1px solid #c7d2fe",
                background: "#eef2ff",
                color: "#4338ca",
                cursor: "pointer",
              }}
            >
              🚀 14-Day Playbook
            </button>
            <button
              onClick={() => handleSendMessage(`What is BOCPD and how does it detect changepoints for ${selectedChannel.name}?`)}
              disabled={isTyping}
              style={{
                fontSize: "11px",
                fontWeight: 600,
                padding: "5px 10px",
                borderRadius: "16px",
                border: "1px solid #fbcfe8",
                background: "#fdf2f8",
                color: "#be185d",
                cursor: "pointer",
              }}
            >
              📈 BOCPD Changepoint
            </button>
            <button
              onClick={() => handleSendMessage(`Which channel is the best audience bridge for ${selectedChannel.name}?`)}
              disabled={isTyping}
              style={{
                fontSize: "11px",
                fontWeight: 600,
                padding: "5px 10px",
                borderRadius: "16px",
                border: "1px solid #e9d5ff",
                background: "#faf5ff",
                color: "#7e22ce",
                cursor: "pointer",
              }}
            >
              🤝 Bridge Partners
            </button>
            <button
              onClick={() => handleSendMessage(`What are commenters requesting for ${selectedChannel.name}?`)}
              disabled={isTyping}
              style={{
                fontSize: "11px",
                fontWeight: 600,
                padding: "5px 10px",
                borderRadius: "16px",
                border: "1px solid #bbf7d0",
                background: "#f0fdf4",
                color: "#15803d",
                cursor: "pointer",
              }}
            >
              💬 Comment Demands
            </button>
          </div>

          {/* Input Box */}
          <div
            style={{
              padding: "12px 14px",
              borderTop: "1px solid #e2e8f0",
              background: "#ffffff",
              display: "flex",
              gap: "8px",
              alignItems: "center",
            }}
          >
            <input
              type="text"
              placeholder={`Ask about ${selectedChannel.name} or research...`}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSendMessage();
              }}
              disabled={isTyping}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "24px",
                border: "1px solid #cbd5e1",
                fontSize: "13px",
                outline: "none",
              }}
            />
            <button
              onClick={() => handleSendMessage()}
              disabled={!inputMessage.trim() || isTyping}
              style={{
                width: "38px",
                height: "38px",
                borderRadius: "50%",
                border: "none",
                background: inputMessage.trim() && !isTyping ? "#2563eb" : "#cbd5e1",
                color: "#ffffff",
                display: "grid",
                placeItems: "center",
                cursor: inputMessage.trim() && !isTyping ? "pointer" : "default",
                fontSize: "14px",
              }}
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </>
  );
};
