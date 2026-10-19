import React from "react";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export const ExecutiveGrowthBriefModal: React.FC<Props> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const handlePrint = () => {
    const briefContent = document.getElementById("printable-brief");
    if (!briefContent) {
      window.print();
      return;
    }

    // Open an isolated, clean printable window
    const printWindow = window.open("", "_blank", "width=850,height=900");
    if (!printWindow) {
      // Fallback if popup blocker is active
      window.print();
      return;
    }

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Trendora - Executive Network Growth Digest</title>
          <style>
            @page {
              size: A4 portrait;
              margin: 15mm;
            }
            body {
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
              color: #0f172a;
              margin: 0;
              padding: 0;
              background: #ffffff;
              -webkit-print-color-adjust: exact !important;
              print-color-adjust: exact !important;
            }
            h1, h2, h3, h4 { margin: 0; color: #0f172a; }
            table { width: 100%; border-collapse: collapse; margin-top: 6px; margin-bottom: 14px; font-size: 11.5px; }
            th, td { padding: 7px 10px; border-bottom: 1px solid #e2e8f0; }
            th { background: #f8fafc !important; font-weight: 700; text-align: left; -webkit-print-color-adjust: exact; }
            .avoid-break { page-break-inside: avoid; break-inside: avoid; }
          </style>
        </head>
        <body>
          ${briefContent.innerHTML}
          <script>
            window.onload = function() {
              window.focus();
              setTimeout(function() {
                window.print();
              }, 250);
            };
          <\/script>
        </body>
      </html>
    `);
    printWindow.document.close();
  };

  return (
    <>
      {/* Global Print Isolation CSS */}
      <style>
        {`
          @media print {
            body * {
              visibility: hidden !important;
            }
            #printable-brief, #printable-brief * {
              visibility: visible !important;
            }
            #printable-brief {
              position: fixed !important;
              left: 0 !important;
              top: 0 !important;
              width: 100% !important;
              max-width: 100% !important;
              margin: 0 !important;
              padding: 20px !important;
              background: #ffffff !important;
              box-shadow: none !important;
              z-index: 999999 !important;
            }
          }
        `}
      </style>

      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(15, 23, 42, 0.75)",
          backdropFilter: "blur(4px)",
          zIndex: 10000,
          display: "grid",
          placeItems: "center",
          padding: "20px",
        }}
        onClick={onClose}
      >
        <div
          style={{
            background: "#ffffff",
            borderRadius: "18px",
            width: "850px",
            maxWidth: "100%",
            maxHeight: "90vh",
            overflowY: "auto",
            padding: "36px",
            boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.4)",
            position: "relative",
            color: "#0f172a",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Modal Controls Bar */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "24px",
              borderBottom: "1px solid #e2e8f0",
              paddingBottom: "16px",
            }}
          >
            <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
              <span style={{ fontSize: "20px" }}>📑</span>
              <div>
                <div style={{ fontSize: "16px", fontWeight: 800 }}>Executive Network Growth Digest</div>
                <div style={{ fontSize: "12px", color: "#64748b" }}>Derana Media Network Portfolio (52 Channels)</div>
              </div>
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <button
                type="button"
                onClick={handlePrint}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 16px",
                  borderRadius: "8px",
                  border: "none",
                  background: "#2563eb",
                  color: "#ffffff",
                  fontSize: "13px",
                  fontWeight: 700,
                  cursor: "pointer",
                  boxShadow: "0 2px 6px rgba(37, 99, 235, 0.3)",
                }}
              >
                🖨️ Print / Save as PDF
              </button>
              <button
                type="button"
                onClick={onClose}
                style={{
                  background: "#f1f5f9",
                  border: "none",
                  borderRadius: "8px",
                  padding: "8px 12px",
                  cursor: "pointer",
                  fontWeight: 700,
                  color: "#64748b",
                }}
              >
                ✕
              </button>
            </div>
          </div>

          {/* Printable Document Body */}
          <div id="printable-brief">
            {/* Executive Header */}
            <div style={{ borderBottom: "2px solid #0f172a", paddingBottom: "14px", marginBottom: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 800, color: "#2563eb", letterSpacing: "1px", textTransform: "uppercase" }}>
                    SLIIT CoEAI Research Framework · J26-DS-334
                  </div>
                  <h1 style={{ fontSize: "24px", fontWeight: 900, margin: "4px 0", color: "#0f172a" }}>
                    Weekly Network Growth Intelligence Brief
                  </h1>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    Autonomous 4-Pillar Cross-Channel Optimization &amp; Allocation Report
                  </div>
                </div>
                <div style={{ textAlign: "right", fontSize: "12px", color: "#64748b" }}>
                  <div>Date: <strong>October 20, 2026</strong></div>
                  <div>Coverage: <strong>52 Channels · 1,682 Videos</strong></div>
                </div>
              </div>
            </div>

            {/* Section 1: Pillar 1 Underperformance Interventions */}
            <div className="avoid-break" style={{ marginBottom: "20px" }}>
              <div style={{ fontSize: "12px", fontWeight: 800, color: "#1d4ed8", textTransform: "uppercase", marginBottom: "8px" }}>
                1. Growth Opportunities &amp; Underperforming Targets (Pillar 1)
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #cbd5e1", textAlign: "left" }}>
                    <th style={{ padding: "8px" }}>Target Channel</th>
                    <th style={{ padding: "8px" }}>Niche</th>
                    <th style={{ padding: "8px", textAlign: "right" }}>Subscribers</th>
                    <th style={{ padding: "8px", textAlign: "right" }}>Views/Sub</th>
                    <th style={{ padding: "8px", textAlign: "right" }}>Niche Benchmark</th>
                    <th style={{ padding: "8px", textAlign: "center" }}>Recovery Prob</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px", fontWeight: 700 }}>eTunes</td>
                    <td style={{ padding: "8px" }}>Music</td>
                    <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>120K</td>
                    <td style={{ padding: "8px", textAlign: "right", color: "#dc2626", fontWeight: 700 }}>0.14</td>
                    <td style={{ padding: "8px", textAlign: "right" }}>0.38</td>
                    <td style={{ padding: "8px", textAlign: "center", fontWeight: 700, color: "#16a34a" }}>78%</td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px", fontWeight: 700 }}>Lokaya Saha Lokayo</td>
                    <td style={{ padding: "8px" }}>Entertainment</td>
                    <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>290K</td>
                    <td style={{ padding: "8px", textAlign: "right", color: "#dc2626", fontWeight: 700 }}>0.19</td>
                    <td style={{ padding: "8px", textAlign: "right" }}>0.44</td>
                    <td style={{ padding: "8px", textAlign: "center", fontWeight: 700, color: "#16a34a" }}>84%</td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px", fontWeight: 700 }}>DAM DERANA</td>
                    <td style={{ padding: "8px" }}>Culture</td>
                    <td style={{ padding: "8px", textAlign: "right", fontFamily: "monospace" }}>95K</td>
                    <td style={{ padding: "8px", textAlign: "right", color: "#dc2626", fontWeight: 700 }}>0.11</td>
                    <td style={{ padding: "8px", textAlign: "right" }}>0.31</td>
                    <td style={{ padding: "8px", textAlign: "center", fontWeight: 700, color: "#16a34a" }}>68%</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Section 2: Pillar 2 Mined Comment Demand */}
            <div className="avoid-break" style={{ marginBottom: "20px" }}>
              <div style={{ fontSize: "12px", fontWeight: 800, color: "#059669", textTransform: "uppercase", marginBottom: "8px" }}>
                2. Quantified Audience Demand Requests (Pillar 2 · 26,513 Comments)
              </div>
              <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "8px", padding: "12px 14px", fontSize: "12px", color: "#166534", lineHeight: "1.6" }}>
                <strong>Top Audience Intent Demand:</strong> 34.2% of parsed public comments actively demand acoustic studio unplugged sessions and deep-dive teledrama character analysis. 72.5% of requests use Sinhala-English code-switching (&quot;Tanglish&quot;), requiring bilingual metadata packaging.
              </div>
            </div>

            {/* Section 3: Pillar 3 Audience Bridge Pairings */}
            <div className="avoid-break" style={{ marginBottom: "20px" }}>
              <div style={{ fontSize: "12px", fontWeight: 800, color: "#7c3aed", textTransform: "uppercase", marginBottom: "8px" }}>
                3. Recommended Weekend Cross-Channel Bridge Schedule (Pillar 3)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "12px" }}>
                <div style={{ background: "#f8fafc", padding: "10px", borderRadius: "6px", borderLeft: "3px solid #8b5cf6" }}>
                  <strong>TV Derana &rarr; eTunes:</strong> Schedule Community Tab spotlight 24h prior to premiere. <em>(Audience Bridge Score: 0.842)</em>
                </div>
                <div style={{ background: "#f8fafc", padding: "10px", borderRadius: "6px", borderLeft: "3px solid #8b5cf6" }}>
                  <strong>Ada Derana 24 &rarr; DAM DERANA:</strong> Broadcast 30s teaser snippet during weekend prime news. <em>(Bridge Score: 0.812)</em>
                </div>
              </div>
            </div>

            {/* Section 4: Pillar 4 Emerging Topic BOCPD & Cannibalization Shield */}
            <div className="avoid-break" style={{ marginBottom: "20px" }}>
              <div style={{ fontSize: "12px", fontWeight: 800, color: "#be185d", textTransform: "uppercase", marginBottom: "8px" }}>
                4. Emerging Topic BOCPD Changepoints &amp; Cannibalization Allocations (Pillar 4)
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #cbd5e1", textAlign: "left" }}>
                    <th style={{ padding: "8px" }}>Emerging Topic</th>
                    <th style={{ padding: "8px" }}>BOCPD Changepoint</th>
                    <th style={{ padding: "8px" }}>Assigned Exclusive Creator</th>
                    <th style={{ padding: "8px" }}>Flagship Bridge Role</th>
                    <th style={{ padding: "8px", textAlign: "right" }}>Views Protected</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px", fontWeight: 700 }}>Acoustic Neo-Folk &amp; Unplugged</td>
                    <td style={{ padding: "8px", color: "#ec4899", fontWeight: 700 }}>t=14 (89.4%)</td>
                    <td style={{ padding: "8px", color: "#15803d", fontWeight: 700 }}>eTunes (Exclusive)</td>
                    <td style={{ padding: "8px" }}>TV Derana (End-Screen)</td>
                    <td style={{ padding: "8px", textAlign: "right", fontWeight: 700, color: "#16a34a" }}>+145,000</td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px", fontWeight: 700 }}>Teledrama Plot Deep-Dives</td>
                    <td style={{ padding: "8px", color: "#ec4899", fontWeight: 700 }}>t=18 (84.1%)</td>
                    <td style={{ padding: "8px", color: "#15803d", fontWeight: 700 }}>Lokaya Saha Lokayo</td>
                    <td style={{ padding: "8px" }}>TV Derana (Pinned Link)</td>
                    <td style={{ padding: "8px", textAlign: "right", fontWeight: 700, color: "#16a34a" }}>+290,000</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Executive Sign-off Footer */}
            <div className="avoid-break" style={{ borderTop: "1px solid #cbd5e1", paddingTop: "12px", display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#64748b" }}>
              <div>Approved by: <strong>Program Director · Derana Media Network</strong></div>
              <div>Generated by: <strong>Trendora AI Copilot (SLIIT CoEAI)</strong></div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
