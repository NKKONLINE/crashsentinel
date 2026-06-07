import { useEffect, useState } from "react";
import axios from "axios";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar, Legend
} from "recharts";

const API = "http://localhost:8000";

const COLORS = ["#ef4444", "#f59e0b", "#22c55e", "#a855f7", "#58a6ff", "#f97316"];

export default function Charts() {
  const [data, setData] = useState(null);

  useEffect(() => {
    axios.get(`${API}/charts`).then(r => setData(r.data));
  }, []);

  if (!data) return (
    <p style={{ color: "#6b7280" }}>Loading charts...</p>
  );

  if (data.daily.length === 0) return (
    <p style={{ color: "#6b7280" }}>
      No data yet. Analyze some logs first to see charts!
    </p>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "32px" }}>

      {/* Crashes Over Time */}
      <div style={{
        background: "#161b22", border: "1px solid #30363d",
        borderRadius: "10px", padding: "24px"
      }}>
        <h3 style={{ color: "#58a6ff", marginTop: 0 }}>📈 Crashes Over Time</h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data.daily}>
            <XAxis dataKey="date" stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={11} />
            <Tooltip
              contentStyle={{ background: "#161b22", border: "1px solid #30363d", color: "#e6edf3" }}
            />
            <Line type="monotone" dataKey="crashes" stroke="#ef4444"
              strokeWidth={2} dot={{ fill: "#ef4444" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>

        {/* Severity Breakdown */}
        <div style={{
          background: "#161b22", border: "1px solid #30363d",
          borderRadius: "10px", padding: "24px"
        }}>
          <h3 style={{ color: "#58a6ff", marginTop: 0 }}>🎯 Severity Breakdown</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={data.severity} dataKey="value" nameKey="name"
                cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${name}: ${value}`}>
                {data.severity.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #30363d", color: "#e6edf3" }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Crash Types */}
        <div style={{
          background: "#161b22", border: "1px solid #30363d",
          borderRadius: "10px", padding: "24px"
        }}>
          <h3 style={{ color: "#58a6ff", marginTop: 0 }}>🔥 Crash Types</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.types}>
              <XAxis dataKey="name" stroke="#6b7280" fontSize={10} />
              <YAxis stroke="#6b7280" fontSize={11} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #30363d", color: "#e6edf3" }}
              />
              <Bar dataKey="value" fill="#58a6ff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

      </div>
    </div>
  );
}