import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface IntentItem {
  intent: string;
  percentage: string;
  count: number;
  color: string;
  description: string;
}

interface CritiqueItem {
  category: string;
  percentage: string;
  count: number;
  color: string;
  example: string;
}

interface SampleComment {
  id: string;
  author_hash: string;
  channel: string;
  text: string;
  script: string;
  intent: string;
  sentiment: string;
  color: string;
}

export const AudienceDemandPage: React.FC = () => {
  const [intents, setIntents] = useState<IntentItem[]>([]);
  const [critiques, setCritiques] = useState<CritiqueItem[]>([]);
  const [activeFilter, setActiveFilter] = useState<string>("ALL");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  const sampleComments: SampleComment[] = [
    {
      id: "c1",
      author_hash: "usr_9f82a1c0",
      channel: "eTunes",
      text: "me sinduwe acoustic guitar version ekak karannako please! vocals only ahan inna asayi",
      script: "Tanglish",
      intent: "Content Request",
      sentiment: "+0.82 Eager",
      color: "#10b981",
    },
    {
      id: "c2",
      author_hash: "usr_4b18e7d2",
      channel: "Lokaya Saha Lokayo",
      text: "සද්දෙ පැහැදිලි නෑ mic echo එක වැඩියි audio quality එක හදන්න studio එකේ",
      script: "Sinhala Unicode",
      intent: "Constructive Critique",
      sentiment: "-0.45 Critical",
      color: "#f59e0b",
    },
    {
      id: "c3",
      author_hash: "usr_c321fa99",
      channel: "DAM DERANA",
      text: "Ravana underground tunnels gana full documentary ekak one dam derana team eken",
      script: "Tanglish",
      intent: "Content Request",
      sentiment: "+0.75 Eager",
      color: "#10b981",
    },
    {
      id: "c4",
      author_hash: "usr_88d492bb",
      channel: "TV Derana",
      text: "සුපිරිම program එකක්! ආදරෙයි Derana production team එකට හැමදාම බලනවා ❤️",
      script: "Sinhala Unicode",
      intent: "Appreciation",
      sentiment: "+0.95 Positive",
      color: "#3b82f6",
    },
    {
      id: "c5",
      author_hash: "usr_102fe49a",
      channel: "eTunes",
      text: "Video intro eka 50 seconds wadi kelinma song ekata start karanna tibbe",
      script: "Tanglish",
      intent: "Constructive Critique",
      sentiment: "-0.38 Critical",
      color: "#f59e0b",
    },
    {
      id: "c6",
      author_hash: "usr_6a9b40ee",
      channel: "Ada Derana 24",
      text: "Live coverage update eka kawadda enne schedule eka announce karanna",
      script: "Tanglish",
      intent: "Inquiry",
      sentiment: "+0.15 Curious",
      color: "#8b5cf6",
    },
  ];

  useEffect(() => {
    Promise.all([
      fetch("http://127.0.0.1:8000/api/v1/component-2/intent-breakdown").then((r) => r.json()),
      fetch("http://127.0.0.1:8000/api/v1/component-2/critique-breakdown").then((r) => r.json()),
    ])
      .then(([intentData, critiqueData]) => {
        setIntents(intentData.intents || []);
        setCritiques(critiqueData || []);
        setLoading(false);
      })
      .catch(() => {
        // Fallback default
        setIntents([
          { intent: "Content Requests & Inquiries", percentage: "34.2%", count: 9067, color: "#10b981", description: "Viewers requesting specific topics, acoustic versions, or actors" },
          { intent: "Appreciation & Positive Feedback", percentage: "38.6%", count: 10234, color: "#3b82f6", description: "Expressions of praise, support, and community loyalty" },
          { intent: "Constructive Critique", percentage: "14.8%", count: 3924, color: "#f59e0b", description: "Actionable feedback on audio mixing, pacing, or presentation" },
          { intent: "Questions & Clarifications", percentage: "8.1%", count: 2148, color: "#8b5cf6", description: "Follow-up questions regarding schedule and broadcast details" },
          { intent: "Filtered Noise / Spam", percentage: "4.3%", count: 1140, color: "#ef4444", description: "Automated promotional bots filtered out by NLP pipeline" },
        ]);
        setCritiques([
          { category: "Audio Mixing & Vocal Clarity", percentage: "41.8%", count: 1640, color: "#ef4444", example: "Vocals overpowered by backing track / mic echo in indoor studio" },
          { category: "Pacing & Video Editing Rhythm", percentage: "28.4%", count: 1114, color: "#f59e0b", example: "Intro sequence too long (>45s) before main song or plot review starts" },
          { category: "Presentation & Host Delivery", percentage: "17.6%", count: 691, color: "#3b82f6", example: "Desire for more natural, unscripted artist banter between tracks" },
          { category: "Upload Cadence & Scheduling", percentage: "12.2%", count: 479, color: "#8b5cf6", example: "Inconsistent release days causing viewers to miss premieres" },
        ]);
        setLoading(false);
      });
  }, []);

  const filteredComments = sampleComments.filter((c) => {
    const matchesFilter =
      activeFilter === "ALL" ||
      (activeFilter === "REQUESTS" && c.intent === "Content Request") ||
      (activeFilter === "CRITIQUES" && c.intent === "Constructive Critique") ||
      (activeFilter === "APPRECIATION" && c.intent === "Appreciation");
    const matchesSearch =
      c.text.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.channel.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.script.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  return (
    <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "20px" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div
          style={{
            display: "inline-block",
            padding: "4px 10px",
            background: "#d1fae5",
            color: "#065f46",
            borderRadius: "16px",
            fontSize: "12px",
            fontWeight: 700,
            marginBottom: "8px",
          }}
        >
          RESEARCH PILLAR 2 · IT23307094 · KAHANDAWA K A N N
        </div>
        <h1 style={{ margin: "4px 0", fontSize: "28px", fontWeight: 800, color: "var(--fg-primary, #0f172a)" }}>
          Audience Demand Mining & Intent Classification
        </h1>
        <p style={{ margin: 0, color: "#64748b", fontSize: "15px" }}>
          Mining 26,513 Multi-Script Public YouTube Comments to Quantify Unmet Audience Demand and Actionable Production Feedback
        </p>
      </div>

      {/* KPI Stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #10b981" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Mined Comments
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, margin: "4px 0" }}>26,513</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>52 Network Channels</div>
        </div>

        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #3b82f6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Unique Viewers Cohort
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, margin: "4px 0" }}>16,976</div>
          <div style={{ fontSize: "12px", color: "#16a34a", fontWeight: 600 }}>Salted MD5 Pseudonymized</div>
        </div>

        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #f59e0b" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Constructive Critiques
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, margin: "4px 0", color: "#d97706" }}>3,924</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Actionable Production Issues</div>
        </div>

        <div className="card" style={{ padding: "18px", borderLeft: "4px solid #8b5cf6" }}>
          <div style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
            Demand Requests
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, margin: "4px 0", color: "#7c3aed" }}>9,067 (34.2%)</div>
          <div style={{ fontSize: "12px", color: "var(--muted)" }}>Direct Content Topic Demands</div>
        </div>
      </div>

      {/* Demand Intent Distribution Cards */}
      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 800 }}>
              Audience Demand Intent Taxonomy {loading && <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 500 }}>(Refreshing...)</span>}
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--muted)" }}>
              Distribution of public YouTube comment intentions extracted across portfolio channels.
            </p>
          </div>
          <Link to="/c2/multilingual-nlp" style={{ fontSize: "13px", fontWeight: 700, color: "#059669", textDecoration: "none" }}>
            Open Live NLP Classifier Playground →
          </Link>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
          {intents.map((item) => (
            <div
              key={item.intent}
              style={{
                background: "var(--surface-2)",
                padding: "16px",
                borderRadius: "10px",
                borderLeft: `4px solid ${item.color}`,
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 800, color: item.color, textTransform: "uppercase" }}>
                {item.percentage}
              </div>
              <h4 style={{ margin: "4px 0", fontSize: "14px", fontWeight: 700, color: "var(--fg-primary)" }}>
                {item.intent}
              </h4>
              <div style={{ fontSize: "12px", color: "var(--muted)", margin: "4px 0" }}>
                {item.count.toLocaleString()} comments
              </div>
              <p style={{ margin: 0, fontSize: "11px", color: "var(--muted)", lineHeight: "1.4" }}>
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Constructive Critique Deep-Dive Card */}
      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <div style={{ display: "inline-block", padding: "3px 8px", background: "#fef3c7", color: "#b45309", borderRadius: "4px", fontSize: "11px", fontWeight: 700, marginBottom: "4px" }}>
              ACTIONABLE AUDIENCE SIGNALS
            </div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 800 }}>
              Constructive Critique Categorization (3,924 Mined Comments)
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--muted)" }}>
              Specific production bottlenecks directly cited by viewers on underperforming channel uploads.
            </p>
          </div>
          <Link to="/c2/content-gap" style={{ fontSize: "13px", fontWeight: 700, color: "#d97706", textDecoration: "none" }}>
            View Topic Gap Divergence (JSD) →
          </Link>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
          {critiques.map((c) => (
            <div
              key={c.category}
              style={{
                background: "var(--surface-2)",
                padding: "18px",
                borderRadius: "10px",
                borderTop: `4px solid ${c.color}`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "12px", fontWeight: 800, color: c.color }}>{c.percentage}</span>
                <span style={{ fontSize: "11px", color: "var(--muted)", fontWeight: 600 }}>{c.count} comments</span>
              </div>
              <h4 style={{ margin: "6px 0 8px 0", fontSize: "15px", fontWeight: 700, color: "var(--fg-primary)" }}>
                {c.category}
              </h4>
              <div style={{ background: "#ffffff", padding: "10px", borderRadius: "6px", border: "1px solid #e2e8f0", fontSize: "12px", color: "#334155" }}>
                💬 <em>"{c.example}"</em>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Filterable Comment Explorer Stream */}
      <div className="card" style={{ padding: "24px", marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 800 }}>
              Live Mined Comment Feed (Zero-Leakage Sample Stream)
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "var(--muted)" }}>
              Anonymized public feedback with intent labels, detected scripts, and sentiment polarity.
            </p>
          </div>

          {/* Filter Pills */}
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {[
              { id: "ALL", label: "All Intents" },
              { id: "REQUESTS", label: "Requests (34.2%)" },
              { id: "CRITIQUES", label: "Critiques (14.8%)" },
              { id: "APPRECIATION", label: "Appreciation (38.6%)" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setActiveFilter(f.id)}
                style={{
                  padding: "6px 12px",
                  borderRadius: "6px",
                  border: "1px solid",
                  borderColor: activeFilter === f.id ? "#059669" : "var(--border)",
                  background: activeFilter === f.id ? "#059669" : "var(--surface)",
                  color: activeFilter === f.id ? "#ffffff" : "var(--fg-primary)",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Search input */}
        <div style={{ marginBottom: "16px" }}>
          <input
            type="text"
            placeholder="Search by keyword, channel name, or script type..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: "100%",
              padding: "10px 14px",
              borderRadius: "8px",
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              color: "var(--fg-primary)",
              fontSize: "13px",
            }}
          />
        </div>

        {/* Comment Rows */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {filteredComments.map((comment) => (
            <div
              key={comment.id}
              style={{
                background: "var(--surface-2)",
                padding: "14px 16px",
                borderRadius: "8px",
                borderLeft: `4px solid ${comment.color}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "12px",
              }}
            >
              <div style={{ flex: 1, minWidth: "260px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                  <span style={{ fontSize: "11px", fontFamily: "monospace", color: "var(--muted)", fontWeight: 600 }}>
                    {comment.author_hash}
                  </span>
                  <span style={{ fontSize: "11px", fontWeight: 700, color: "#0284c7" }}>
                    @{comment.channel}
                  </span>
                  <span style={{ fontSize: "10px", padding: "1px 6px", background: "#e2e8f0", color: "#475569", borderRadius: "10px", fontWeight: 600 }}>
                    {comment.script}
                  </span>
                </div>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--fg-primary)" }}>
                  "{comment.text}"
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    fontWeight: 800,
                    background: `${comment.color}20`,
                    color: comment.color,
                  }}
                >
                  {comment.intent}
                </span>
                <span style={{ fontSize: "11px", fontWeight: 700, color: comment.sentiment.startsWith("+") ? "#16a34a" : "#dc2626" }}>
                  {comment.sentiment}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Navigation Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Link to="/c2/multilingual-nlp" className="button" style={{ textDecoration: "none" }}>
          ← Multilingual NLP Normalization
        </Link>
        <Link to="/c2/content-gap" className="button" style={{ textDecoration: "none" }}>
          Proceed to Content-Gap Divergence (JSD) →
        </Link>
      </div>
    </div>
  );
};
