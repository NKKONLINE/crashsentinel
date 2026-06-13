import Charts from "./Charts";
import { useState, useEffect } from "react";
import axios from "axios";

const API = "http://localhost:8888";

const SEVERITY_COLORS = {
  low: { bg: "#0d2b1a", border: "#22c55e", text: "#22c55e" },
  medium: { bg: "#2b1f0a", border: "#f59e0b", text: "#f59e0b" },
  high: { bg: "#2b0f0f", border: "#ef4444", text: "#ef4444" },
  critical: { bg: "#1e0b2b", border: "#a855f7", text: "#a855f7" },
};

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: "#161b22", border: `1px solid ${color}`,
      borderRadius: "10px", padding: "20px", textAlign: "center",
      minWidth: "130px", flex: 1
    }}>
      <div style={{ fontSize: "36px", fontWeight: "bold", color }}>{value}</div>
      <div style={{ color: "#8b949e", marginTop: "6px", fontSize: "13px" }}>{label}</div>
    </div>
  );
}

function AlertBanner({ alert, onDismiss }) {
  const confidence = Math.round(alert.confidence * 100);
  return (
    <div style={{
      background: "#2b1a0a", border: "1px solid #f97316",
      borderRadius: "10px", padding: "16px 20px",
      marginBottom: "12px", display: "flex",
      justifyContent: "space-between", alignItems: "flex-start"
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
          <span style={{ fontSize: "18px" }}></span>
          <strong style={{ color: "#f97316" }}>
            Predictive Alert — {confidence}% confidence
          </strong>
        </div>
        <p style={{ color: "#e2c9b0", margin: "0 0 6px 0" }}>{alert.message}</p>
        <small style={{ color: "#6b7280" }}>
          Triggered by: {alert.matched_symptom}
        </small>
      </div>
      <button onClick={() => onDismiss(alert.id)} style={{
        background: "#374151", color: "#9ca3af", border: "none",
        padding: "6px 14px", borderRadius: "6px", cursor: "pointer",
        marginLeft: "16px", whiteSpace: "nowrap"
      }}>
        Dismiss
      </button>
    </div>
  );
}

function CrashCard({ report, isSelected, onClick }) {
  const colors = SEVERITY_COLORS[report.severity] || SEVERITY_COLORS.medium;
  return (
    <div onClick={onClick} style={{
      background: isSelected ? "#1f2937" : colors.bg,
      border: `1px solid ${colors.border}`,
      borderRadius: "8px", padding: "14px",
      marginBottom: "10px", cursor: "pointer",
      transition: "all 0.2s"
    }}>
      <div style={{ color: colors.text, fontWeight: "bold", marginBottom: "4px" }}>
        {report.crash_type}
      </div>
      <div style={{ color: "#8b949e", fontSize: "12px", marginBottom: "4px" }}>
        {new Date(report.timestamp).toLocaleString()}
      </div>
      <div style={{
        display: "inline-block", background: colors.bg,
        border: `1px solid ${colors.border}`, color: colors.text,
        fontSize: "11px", padding: "2px 8px", borderRadius: "4px"
      }}>
        {report.severity.toUpperCase()}
      </div>
    </div>
  );
}

function CrashDetail({ report }) {
  const colors = SEVERITY_COLORS[report.severity] || SEVERITY_COLORS.medium;
  return (
    <div style={{
      background: "#161b22", border: "1px solid #30363d",
      borderRadius: "10px", padding: "24px", height: "100%"
    }}>
      <h2 style={{ color: colors.text, marginTop: 0 }}>{report.crash_type}</h2>
      <div style={{ marginBottom: "16px" }}>
        <span style={{
          background: colors.bg, border: `1px solid ${colors.border}`,
          color: colors.text, padding: "3px 10px", borderRadius: "4px",
          fontSize: "12px"
        }}>
          {report.severity.toUpperCase()}
        </span>
        <span style={{ color: "#6b7280", fontSize: "12px", marginLeft: "12px" }}>
          {new Date(report.timestamp).toLocaleString()}
        </span>
      </div>

      <Section title=" Root Cause" content={report.root_cause} />
      <Section title=" AI Explanation" content={report.explanation} />

      {report.symptoms?.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <h4 style={{ color: "#58a6ff", marginBottom: "8px" }}>⚡ Precursor Symptoms</h4>
          <ul style={{ color: "#c9d1d9", paddingLeft: "20px", lineHeight: "1.8" }}>
            {report.symptoms.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      <div style={{ marginTop: "16px" }}>
        <h4 style={{ color: "#58a6ff", marginBottom: "8px" }}>📄 Raw Log</h4>
        <pre style={{
          background: "#0d1117", padding: "12px", borderRadius: "6px",
          color: "#7ee787", fontSize: "12px", overflowX: "auto",
          whiteSpace: "pre-wrap", wordBreak: "break-all"
        }}>
          {report.raw_log}
        </pre>
      </div>
    </div>
  );
}

function Section({ title, content }) {
  return (
    <div style={{ marginBottom: "16px" }}>
      <h4 style={{ color: "#58a6ff", marginBottom: "8px" }}>{title}</h4>
      <p style={{
        background: "#0d1117", padding: "12px", borderRadius: "6px",
        color: "#c9d1d9", lineHeight: "1.7", margin: 0
      }}>
        {content}
      </p>
    </div>
  );
}

export default function App() {
  const [reports, setReports] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState({});
  const [summary, setSummary] = useState("");
  const [selected, setSelected] = useState(null);
  const [manualLog, setManualLog] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");

  useEffect(() => {
    fetchAll();
    const interval = setInterval(() => {
      fetchAlerts();
      fetchStats();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchAll = () => {
    fetchReports();
    fetchAlerts();
    fetchStats();
    fetchSummary();
  };

  const fetchReports = async () => {
    const r = await axios.get(`${API}/reports`);
    setReports(r.data);
    if (r.data.length > 0 && !selected) setSelected(r.data[0]);
  };

  const fetchAlerts = async () => {
    const r = await axios.get(`${API}/alerts`);
    setAlerts(r.data);
  };

  const fetchStats = async () => {
    const r = await axios.get(`${API}/stats`);
    setStats(r.data);
  };

  const fetchSummary = async () => {
    const r = await axios.get(`${API}/summary`);
    setSummary(r.data.summary);
  };

  const dismissAlert = async (id) => {
    await axios.post(`${API}/alerts/${id}/dismiss`);
    fetchAlerts();
  };

  const analyzeManual = async () => {
    if (!manualLog.trim()) return;
    setAnalyzing(true);
    try {
      await axios.post(`${API}/analyze`, { log: manualLog });
      setManualLog("");
      setTimeout(fetchAll, 1000);
    } finally {
      setAnalyzing(false);
    }
  };

  const tabStyle = (tab) => ({
    padding: "8px 20px", borderRadius: "6px", cursor: "pointer",
    border: "none", fontFamily: "monospace", fontSize: "14px",
    background: activeTab === tab ? "#58a6ff" : "#21262d",
    color: activeTab === tab ? "#0d1117" : "#c9d1d9",
    fontWeight: activeTab === tab ? "bold" : "normal"
  });

  return (
    <div style={{
      fontFamily: "monospace", background: "#0d1117",
      color: "#e6edf3", minHeight: "100vh", padding: "24px"
    }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", borderBottom: "1px solid #30363d",
        paddingBottom: "16px", marginBottom: "24px"
      }}>
        <div>
          <h1 style={{ margin: 0, color: "#58a6ff" }}> CrashSentinel</h1>
          <small style={{ color: "#6b7280" }}>
            Local AI Crash Detection powered by Gemma 4
          </small>
        </div>
        <button onClick={fetchAll} style={{
          background: "#21262d", color: "#58a6ff", border: "1px solid #30363d",
          padding: "8px 16px", borderRadius: "6px", cursor: "pointer",
          fontFamily: "monospace"
        }}>
          ↻ Refresh
        </button>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div style={{ marginBottom: "24px" }}>
          <h3 style={{ color: "#f97316", marginBottom: "12px" }}>
             Active Alerts ({alerts.length})
          </h3>
          {alerts.map(a => (
            <AlertBanner key={a.id} alert={a} onDismiss={dismissAlert} />
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "24px" }}>
        <button style={tabStyle("dashboard")} onClick={() => setActiveTab("dashboard")}>
          Dashboard
        </button>
        <button style={tabStyle("reports")} onClick={() => setActiveTab("reports")}>
          Reports {reports.length > 0 && `(${reports.length})`}
        </button>
        <button style={tabStyle("charts")} onClick={() => setActiveTab("charts")}>
          Charts
        </button>
        <button style={tabStyle("analyze")} onClick={() => setActiveTab("analyze")}>
          Analyze Log
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === "dashboard" && (
        <div>
          {/* Stats */}
          <div style={{ display: "flex", gap: "16px", marginBottom: "24px", flexWrap: "wrap" }}>
            <StatCard label="Total Crashes" value={stats.total_crashes ?? 0} color="#58a6ff" />
            <StatCard label="Critical" value={stats.critical ?? 0} color="#a855f7" />
            <StatCard label="High Severity" value={stats.high ?? 0} color="#ef4444" />
            <StatCard label="Active Alerts" value={stats.active_alerts ?? 0} color="#f97316" />
          </div>

          {/* Summary */}
          <div style={{
            background: "#161b22", border: "1px solid #30363d",
            borderRadius: "10px", padding: "20px"
          }}>
            <h3 style={{ color: "#58a6ff", marginTop: 0 }}>
              🤖 AI System Health Summary
            </h3>
            <p style={{ color: "#c9d1d9", lineHeight: "1.8", margin: 0 }}>
              {summary || "Generating summary..."}
            </p>
          </div>
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === "reports" && (
        <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "16px" }}>
          <div style={{ overflowY: "auto", maxHeight: "70vh" }}>
            {reports.length === 0 ? (
              <p style={{ color: "#6b7280" }}>No crash reports yet.</p>
            ) : (
              reports.map(r => (
                <CrashCard
                  key={r.id} report={r}
                  isSelected={selected?.id === r.id}
                  onClick={() => setSelected(r)}
                />
              ))
            )}
          </div>
          <div>
            {selected
              ? <CrashDetail report={selected} />
              : <p style={{ color: "#6b7280" }}>Select a crash report to view details.</p>
            }
          </div>
        </div>
      )}
      {/* Charts Tab */}
        {activeTab === "charts" && (
           <Charts />
        )}
      {/* Analyze Tab */}
      {activeTab === "analyze" && (
        <div style={{
          background: "#161b22", border: "1px solid #30363d",
          borderRadius: "10px", padding: "24px"
        }}>
          <h3 style={{ color: "#58a6ff", marginTop: 0 }}>
            Manually Analyze a Log
          </h3>
          <p style={{ color: "#8b949e" }}>
            Paste any crash log or error message and Gemma will analyze it.
          </p>
          <textarea
            value={manualLog}
            onChange={e => setManualLog(e.target.value)}
            placeholder="Paste your crash log here..."
            style={{
              width: "100%", height: "200px", background: "#0d1117",
              color: "#7ee787", border: "1px solid #30363d",
              borderRadius: "6px", padding: "12px", fontFamily: "monospace",
              fontSize: "13px", resize: "vertical", boxSizing: "border-box"
            }}
          />
          <button
            onClick={analyzeManual}
            disabled={analyzing || !manualLog.trim()}
            style={{
              marginTop: "12px", background: analyzing ? "#21262d" : "#58a6ff",
              color: analyzing ? "#6b7280" : "#0d1117", border: "none",
              padding: "10px 24px", borderRadius: "6px", cursor: analyzing ? "not-allowed" : "pointer",
              fontFamily: "monospace", fontWeight: "bold", fontSize: "14px"
            }}
          >
            {analyzing ? " Analyzing..." : " Analyze with Gemma"}
          </button>
        </div>
      )}
    </div>
  );
}