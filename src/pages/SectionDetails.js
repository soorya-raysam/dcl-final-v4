import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import * as XLSX from "xlsx";
import { saveAs } from "file-saver";
import "../App.css";
import {
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function SectionDetails() {
  const { product, section } = useParams();
  const navigate = useNavigate();

  const decodedProduct = decodeURIComponent(product);
  const decodedSection = decodeURIComponent(section);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [filter, setFilter] = useState("All");
  const [alarms, setAlarms] = useState([]);
  const [loadingAlarms, setLoadingAlarms] = useState(true);
  const [diskHistory, setDiskHistory] = useState([]);

  // ✅ Breadcrumb navigation
  const Breadcrumb = () => (
    <div
      style={{
        fontSize: "0.95rem",
        color: "#9ca3af",
        marginBottom: "1rem",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <div>
        <span
          style={{ cursor: "pointer", textDecoration: "underline" }}
          onClick={() => navigate("/")}
        >
          🏠 Home
        </span>{" "}
        /{" "}
        <span
          style={{ cursor: "pointer", textDecoration: "underline" }}
          onClick={() => navigate(`/dashboard/${encodeURIComponent(decodedProduct)}`)}
        >
          {decodedProduct}
        </span>{" "}
        / <strong>{decodedSection}</strong>
      </div>
    </div>
  );

  // --- Download Report (Excel) ---
  const handleDownloadExcel = (tableId, filenamePrefix) => {
    const table = document.getElementById(tableId);
    if (!table) {
      alert("No table data to export!");
      return;
    }
    const workbook = XLSX.utils.table_to_book(table, { sheet: "Report" });
    const now = new Date();
    const timestamp =
      now.toISOString().split("T")[0] + "_" + now.toLocaleTimeString().replace(/:/g, "-");
    const filename = `${filenamePrefix}_Report_${timestamp}.xlsx`;
    const wbout = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
    saveAs(new Blob([wbout], { type: "application/octet-stream" }), filename);
  };

  // --- Fetch Data ---
  const fetchData = async () => {
    try {
      setRefreshing(true);
      const res = await fetch(`${process.env.REACT_APP_API_URL}get-live-health-data`);
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date().toLocaleString());
    } catch (err) {
      console.error("❌ Error fetching live data:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const fetchAlarms = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL}get-alarms-data`);
      const json = await res.json();
      setAlarms(json);
    } catch (err) {
      console.error("Error fetching alarms:", err);
    } finally {
      setLoadingAlarms(false);
    }
  };

  useEffect(() => {
    fetchData();
    if (decodedSection === "Alarms") fetchAlarms();
  }, [decodedSection]);

  // --- Disk Utilisation History ---
  useEffect(() => {
    if (data?.disk_utilisation) {
      const diskOutput = data?.disk_utilisation["df -h"] || data?.disk_utilisation["df -k"];
      const lines = diskOutput?.split("\n").filter((l) => /\d+%/.test(l)) || [];
      const usageValues = lines
        .map((line) => {
          const match = line.match(/\s(\d+)%/);
          return match ? parseInt(match[1]) : null;
        })
        .filter((v) => v !== null);

      if (usageValues.length > 0) {
        const avgUsage = usageValues.reduce((a, b) => a + b, 0) / usageValues.length;
        setDiskHistory((prev) => [
          ...prev.slice(-20),
          { time: new Date().toLocaleTimeString(), usage: avgUsage },
        ]);
      }
    }
  }, [data]);

  // --- Helpers ---
  const parseDfOutput = (text) => {
    if (!text) return { headers: [], rows: [] };
    const lines = text.replace(/\r\n/g, "\n").trim().split("\n").filter(Boolean);
    if (lines.length < 2) return { headers: [], rows: [] };
    const dfRegex =
      /^(\S+)\s+([\d.]+[A-ZKMGTP]?)\s+([\d.]+[A-ZKMGTP]?)\s+([\d.]+[A-ZKMGTP]?)\s+(\d+%)\s+(.+)$/;
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const match = dfRegex.exec(lines[i]);
      if (match) rows.push([match[1], match[2], match[3], match[4], match[5], match[6]]);
    }
    return { headers: ["Filesystem", "Size", "Used", "Avail", "Use%", "Mounted on"], rows };
  };

  const parseServerStatus = (text) => {
    if (!text) return null;
    const clusterMatch = text.match(/Cluster ID:\s*(\S+)/i);
    const cmMatch = text.match(/\n\s*(cm\d+)\s*\n/i);
    const dataPairs = {};
    const regex =
      /ID:\s*([^\n]+)|Mode:\s*([^\n]+)|Major Alarms:\s*([^\n]+)|Minor Alarms:\s*([^\n]+)|Control Network:\s*([^\n]+)|Server Hardware:\s*([^\n]+)|Processes:\s*([^\n]+)/gi;
    let match;
    while ((match = regex.exec(text)) !== null) {
      if (match[1]) dataPairs["ID"] = match[1].trim();
      if (match[2]) dataPairs["Mode"] = match[2].trim();
      if (match[3]) dataPairs["Major Alarms"] = match[3].trim();
      if (match[4]) dataPairs["Minor Alarms"] = match[4].trim();
      if (match[5]) dataPairs["Control Network"] = match[5].trim();
      if (match[6]) dataPairs["Server Hardware"] = match[6].trim();
      if (match[7]) dataPairs["Processes"] = match[7].trim();
    }
    return {
      cluster: clusterMatch ? clusterMatch[1] : "Unknown",
      cmName: cmMatch ? cmMatch[1] : "Unknown",
      tableData: dataPairs,
    };
  };

  const getLevelColor = (sev) => {
    switch (sev) {
      case "Critical":
        return "#dc2626";
      case "Major":
        return "#7e22ce";
      case "Minor":
        return "#f59e0b";
      default:
        return "#9ca3af";
    }
  };

  if (loading) return <div className="loading">Loading live data...</div>;
  if (!data) return <div className="loading">No data received.</div>;

  // --- Render ---
  return (
    <div className="app-container">


      <Breadcrumb />

      {/* Buttons */}
      <div
        style={{
          position: "absolute",
          top: 24,
          right: 32,
          display: "flex",
          gap: "10px",
        }}
      >
        <button className="fancy-button" onClick={fetchData} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "🔄 Refresh"}
        </button>
        <button
          className="fancy-button"
          onClick={() =>
            handleDownloadExcel(
              "report-table",
              `${decodedProduct}_${decodedSection.replace(/\s+/g, "_")}`
            )
          }
        >
          💾 Download Report
        </button>
      </div>

      <h1 className="dashboard-title">
        {decodedProduct} – {decodedSection}
      </h1>

      {/* ✅ Last Refreshed Timestamp */}
      {lastUpdated && (
        <div
          style={{
            textAlign: "center",
            color: "#9ca3af",
            marginBottom: "1rem",
            fontSize: "0.9rem",
          }}
        >
          ⏱️ Last Refreshed: {lastUpdated}
        </div>
      )}

      {/* Disk Utilisation */}
      {decodedSection.includes("Disk Utilisation") && (() => {
        const key = decodedSection.includes("(df -h)") ? "df -h" : "df -k";
        const diskOutput = data?.disk_utilisation?.[key] || "";
        const { rows } = parseDfOutput(diskOutput);
        return (
          <>
            <div className="data-table-container">
              <table id="report-table" className="data-table">
                <thead>
                  <tr>
                    {["Filesystem", "Size", "Used", "Avail", "Use%", "Mounted on"].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      {r.map((c, j) => (
                        <td key={j}>{c}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: "2rem" }}>
              <h2 style={{ textAlign: "center", color: "#f9fafb" }}>
                Real-Time Disk Utilisation Trend
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={diskHistory}>
                  <CartesianGrid stroke="#ccc" />
                  <XAxis dataKey="time" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Line type="monotone" dataKey="usage" stroke="#2563eb" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </>
        );
      })()}

      {/* Server Status */}
      {decodedSection === "Server Status" && (() => {
        const parsed = parseServerStatus(data?.server_status || "");
        if (!parsed) return <p>No server data available.</p>;
        const { cluster, cmName, tableData } = parsed;
        const entries = Object.entries(tableData);
        return (
          <>
            <div
              style={{
                textAlign: "center",
                marginBottom: "1rem",
                color: "#facc15",
                fontWeight: "600",
              }}
            >
              <p>Cluster ID: {cluster}</p>
              <p>CM Name: {cmName}</p>
            </div>
            <div className="data-table-container">
              <table id="report-table" className="data-table">
                <thead>
                  <tr>{entries.map(([key]) => <th key={key}>{key}</th>)}</tr>
                </thead>
                <tbody>
                  <tr>{entries.map(([_, val], i) => <td key={i}>{val}</td>)}</tr>
                </tbody>
              </table>
            </div>
          </>
        );
      })()}

      {/* Alarms */}
{/* Alarms */}
{decodedSection === "Alarms" && (() => {
  // Ensure alarms is always an array
  const alarmsArray = Array.isArray(alarms)
    ? alarms
    : typeof alarms === "object" && alarms !== null
    ? [alarms]
    : [];

  const filtered =
    filter === "All"
      ? alarmsArray
      : alarmsArray.filter((a) => a?.Severity === filter);

  if (!Array.isArray(filtered) || filtered.length === 0) {
    return (
      <div style={{ textAlign: "center", marginTop: "2rem", color: "#9ca3af" }}>
        No alarms available.
      </div>
    );
  }

  return (
    <>
      <div style={{ textAlign: "center", marginBottom: "1rem" }}>
        {["All", "Critical", "Major", "Minor"].map((sev) => (
          <button
            key={sev}
            className={`fancy-button ${filter === sev ? "active" : ""}`}
            onClick={() => setFilter(sev)}
          >
            {sev}
          </button>
        ))}
      </div>
      <div className="data-table-container">
        <table id="report-table" className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>EvtID</th>
              <th>Level</th>
              <th>Ack</th>
              <th>Date</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a, i) => (
              <tr key={i}>
                <td>{a.ID || "-"}</td>
                <td>{a.Source || "-"}</td>
                <td>{a.EvtID || "-"}</td>
                <td style={{ color: getLevelColor(a.Severity || "Normal") }}>
                  {a.Level || a.Severity || "Normal"}
                </td>
                <td>{a.Ack || "-"}</td>
                <td>{a.Date || "-"}</td>
                <td style={{ whiteSpace: "pre-wrap" }}>{a.Description || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
})()}


      {/* Uptime and Backup */}
      {(decodedSection === "Uptime" || decodedSection === "Backup") && (() => {
        const key = decodedSection === "Uptime" ? "system_uptime" : "backup_status";
        const content = data?.[key] || "No data available.";
        return (
          <div className="status-box normal" style={{ textAlign: "center", fontSize: "1.1rem" }}>
            <p>{content}</p>
          </div>
        );
      })()}
    </div>
  );
}
