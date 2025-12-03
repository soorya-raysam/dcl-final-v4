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
          // onClick={() => navigate("/")}
          onClick={() => {
            sessionStorage.setItem("viewOnlyMode", "true");
            navigate("/");
          }}
          
        >
          🏠 Home
        </span>{" "}
        /{" "}
        <span
          style={{ cursor: "pointer", textDecoration: "underline" }}
          onClick={() => {
            sessionStorage.setItem("viewOnlyMode", "true");
            navigate(`/dashboard/${encodeURIComponent(decodedProduct)}`);
          }}
          
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
  // --- Fetch Data (small / targeted fetch) ---
  const fetchData = async () => {
    try {
      setRefreshing(true);

      // get creds from localStorage (TableView saves these)
      const ip = localStorage.getItem("ssh_ip");
      const password = localStorage.getItem("ssh_password");

      if (!ip || !password) {
        console.warn("No IP/password available in localStorage — falling back to GET");
      }

      // map section → endpoint
      const sectionLower = decodedSection.toLowerCase();
      let endpoint = null;
      let options = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip, password }),
      };

      if (sectionLower.includes("uptime")) {
        endpoint = `${process.env.REACT_APP_API_URL}health/uptime`;
      } else if (sectionLower.includes("disk utilisation") || sectionLower.includes("df -h") || sectionLower.includes("df -k")) {
        // fetch both df -h and df -k
        endpoint = `${process.env.REACT_APP_API_URL}health/disk`;
      } else if (sectionLower.includes("server status")) {
        endpoint = `${process.env.REACT_APP_API_URL}health/server-status`;
      } else if (sectionLower === "alarms") {
        endpoint = `${process.env.REACT_APP_API_URL}health/alarms`;
      } else if (sectionLower.includes("backup")) {
        endpoint = `${process.env.REACT_APP_API_URL}health/backup`;
      } else {
        // fallback to original all-in-one endpoint for anything else
        endpoint = `${process.env.REACT_APP_API_URL}get-live-health-data`;
      }

      const res = await fetch(endpoint, options);
      const json = await res.json();

      // Normalize response to previous 'data' shape expected by this component
      // Only populate keys relevant to the section to avoid UI code changes.
      const normalized = { ...data }; // keep old data if present

      if (endpoint.endsWith("/health/uptime")) {
        normalized.system_uptime = json.system_uptime || json.raw || "";
      } else if (endpoint.endsWith("/health/disk")) {
        // your backend returns { "df -h": [...], "df -k": [...] }
        normalized.disk_utilisation = json;
      } else if (endpoint.endsWith("/health/server-status")) {
        normalized.server_status = json.server_status || "";
      } else if (endpoint.endsWith("/health/alarms")) {
        normalized.alarms = json.alarms_parsed || json.alarms_raw || [];
      } else if (endpoint.endsWith("/health/backup")) {
        normalized.backup_status = json.backup_status || "";
      } else {
        // fallback to whole payload shape
        Object.assign(normalized, json);
      }

      setData(normalized);
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
      const rawDisk = data?.disk_utilisation["df -h"] || data?.disk_utilisation["df -k"];

      let diskText = "";
      if (Array.isArray(rawDisk)) {
        diskText =
          rawDisk
            .map((row) => `${row.Filesystem} ${row.Size} ${row.Used} ${row.Avail} ${row["Use%"]} ${row.Mounted_on}`)
            .join("\n");
      } else if (typeof rawDisk === "string") {
        diskText = rawDisk;
      }
      
      const lines = diskText.split("\n").filter((l) => /\d+%/.test(l));
      
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
  // const parseDfOutput = (text) => {
  //   if (!text) return { headers: [], rows: [] };
  //   const lines = text.replace(/\r\n/g, "\n").trim().split("\n").filter(Boolean);
  //   if (lines.length < 2) return { headers: [], rows: [] };
  //   const dfRegex =
  //     /^(\S+)\s+([\d.]+[A-ZKMGTP]?)\s+([\d.]+[A-ZKMGTP]?)\s+([\d.]+[A-ZKMGTP]?)\s+(\d+%)\s+(.+)$/;
  //   const rows = [];
  //   for (let i = 1; i < lines.length; i++) {
  //     const match = dfRegex.exec(lines[i]);
  //     if (match) rows.push([match[1], match[2], match[3], match[4], match[5], match[6]]);
  //   }
  //   return { headers: ["Filesystem", "Size", "Used", "Avail", "Use%", "Mounted on"], rows };
  // };

  const parseDfArray = (arr) => {
    if (!Array.isArray(arr)) return { headers: [], rows: [] };
  
    const headers = ["Filesystem", "Size", "Used", "Avail", "Use%", "Mounted on"];
  
    const rows = arr.map(item => [
      item["Filesystem"] || "",
      item["Size"] || "",
      item["Used"] || "",
      item["Avail"] || "",
      item["Use%"] || "",
      item["Mounted on"] || "",   // ✔ correct key from backend
    ]);
  
    return { headers, rows };
  };
  


  

// parseServerStatus - robust parser for single or two-column Server Status output
// parseServerStatus - supports single or two-column server output,
// returns cluster, metadata, and servers array. Includes Processor Ethernet and PE Priority.
function parseServerStatus(raw) {
  if (!raw) return null;

  const text = raw.replace(/\r/g, "");
  const lines = text.split("\n").map((l) => l.replace(/\u00A0/g, " "));

  // ----------------------------
  // METADATA: look for top-level key: value fields
  // ----------------------------
  const metadataKeys = [
    "Cluster ID",
    "Duplication",
    "Standby Busied\\?",
    "Standby Refreshed\\?",
    "Standby Shadowing",
    "Duplication Link",
    "Elapsed Time since Init/Interchange"
  ];
  const metadata = {};
  metadataKeys.forEach((k) => {
    const re = new RegExp(k + "\\s*:\\s*(.+)", "i");
    const m = text.match(re);
    metadata[k.replace(/\s*\?$/, "")] = m ? m[1].trim() : ""; // store without trailing ? in key
  });

  // cluster quick extract (legacy)
  const clusterMatch = text.match(/Cluster ID:\s*([^\s]+)/i);
  const cluster = clusterMatch ? clusterMatch[1] : metadata["Cluster ID"] || "Unknown";

  // find the "names" / two-column names line if present (big gap between two names)
  let namesLineIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (/\s{6,}/.test(ln) && ln.trim().length > 0) {
      const gap = ln.match(/\s{6,}/);
      const left = ln.slice(0, gap.index).trim();
      const right = ln.slice(gap.index + gap[0].length).trim();
      if (left && right) {
        namesLineIndex = i;
        break;
      }
    }
  }

  // helper to parse key:value lines into object
  const parseKeyValueLines = (arrLines) => {
    const obj = {};
    for (let l of arrLines) {
      const line = l.trim();
      if (!line) continue;
      const m = line.match(/^([A-Za-z0-9 #%\.\-\/()&]+)\s*:\s*(.*)$/);
      if (m) {
        const key = m[1].trim();
        const val = m[2].trim();
        obj[key] = val;
      } else {
        // continuation heuristic: append to last key if present
        const lastKey = Object.keys(obj).slice(-1)[0];
        if (lastKey) obj[lastKey] = (obj[lastKey] + " " + line).trim();
      }
    }
    return obj;
  };

  // ensure server table contains the standard columns we'll show (even if empty)
  const ensureStandardColumns = (obj) => {
    const required = [
      "ID",
      "Mode",
      "Major Alarms",
      "Minor Alarms",
      "Control Network",
      "Processor Ethernet",
      "PE Priority",
      "Server Hardware",
      "Processes"
    ];
    required.forEach((k) => {
      if (!(k in obj)) obj[k] = "";
    });
    return obj;
  };

  // CASE: two-column layout found
  if (namesLineIndex >= 0) {
    const nameLine = lines[namesLineIndex];
    const gapMatch = nameLine.match(/\s{6,}/);
    const splitIdx = gapMatch ? gapMatch.index + gapMatch[0].length : Math.floor(nameLine.length / 2);

    const leftName = nameLine.slice(0, splitIdx).trim() || "Server 1";
    const rightName = nameLine.slice(splitIdx).trim() || "Server 2";

    const leftLines = [];
    const rightLines = [];

    for (let i = namesLineIndex + 1; i < lines.length; i++) {
      const ln = lines[i];
      if (!ln || !ln.trim()) continue;
      const leftPart = ln.length >= splitIdx ? ln.slice(0, splitIdx) : ln;
      const rightPart = ln.length > splitIdx ? ln.slice(splitIdx) : "";
      const leftTrim = leftPart.trim();
      const rightTrim = rightPart.trim();
      if (leftTrim) leftLines.push(leftTrim);
      if (rightTrim) rightLines.push(rightTrim);
    }

    const leftObj = ensureStandardColumns(parseKeyValueLines(leftLines));
    const rightObj = ensureStandardColumns(parseKeyValueLines(rightLines));

    const servers = [];
    if (Object.keys(leftObj).length > 0) servers.push({ name: leftName, tableData: leftObj });
    if (Object.keys(rightObj).length > 0) servers.push({ name: rightName, tableData: rightObj });

    return {
      cluster,
      metadata,
      cmNames: servers.map((s) => s.name),
      servers
    };
  }

  // FALLBACK: single-table parsing (old behavior, but with new columns ensured)
  const dataLines = [];
  for (const l of lines) {
    const trimmed = l.trim();
    if (!trimmed) continue;
    if (/^(ID:|Mode:|Major Alarms:|Minor Alarms:|Control Network:|Processor Ethernet:|PE Priority:|Server Hardware:|Processes:)/i.test(trimmed)) {
      dataLines.push(trimmed);
    }
  }
  const tableData = ensureStandardColumns(parseKeyValueLines(dataLines));

  // Also try to detect a cm name
  const cmMatch = text.match(/\b(cm\d+)\b/i);
  const cmName = cmMatch ? cmMatch[1] : "Unknown";

  return {
    cluster,
    metadata,
    cmNames: [cmName],
    servers: [{ name: cmName, tableData }]
  };
}






  

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
// backend may return array or string
const diskOutput = data?.disk_utilisation?.[key];

// Normalize
let text = "";
if (Array.isArray(diskOutput)) {
  text =
    "Filesystem Size Used Avail Use% Mounted_on\n" +
    diskOutput
      .map(
        (row) =>
          `${row.Filesystem} ${row.Size} ${row.Used} ${row.Avail} ${row["Use%"]} ${row.Mounted_on}`
      )
      .join("\n");
} else if (typeof diskOutput === "string") {
  text = diskOutput;
} else {
  text = "";
}

// const { rows } = parseDfOutput(text || "");

const dfArray = data?.disk_utilisation?.[key] || [];
const { headers, rows } = parseDfArray(dfArray);



        return (
          <>
            <div className="data-table-container">
              <table id="report-table" className="data-table">
                <thead>
                  <tr>
                    {/* {["Filesystem", "Size", "Used", "Avail", "Use%", "Mounted on"].map((h) => (
                      <th key={h}>{h}</th>
                    ))} */}

                      {headers.map((h) => <th key={h}>{h}</th>)}
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

  const { cluster, metadata, servers } = parsed;

  return (
    <>
      <div style={{ textAlign: "center", marginBottom: "1rem", color: "#facc15", fontWeight: 600 }}>
        <p>Cluster ID: {metadata["Cluster ID"] || cluster}</p>
        <p>Duplication: {metadata["Duplication"] || ""}</p>
        <p>Standby Busied?: {metadata["Standby Busied"] || ""}</p>
        <p>Standby Refreshed?: {metadata["Standby Refreshed"] || ""}</p>
        <p>Standby Shadowing: {metadata["Standby Shadowing"] || ""}</p>
        <p>Duplication Link: {metadata["Duplication Link"] || ""}</p>
        <p>Elapsed Time since Init/Interchange: {metadata["Elapsed Time since Init/Interchange"] || ""}</p>
      </div>

      {servers.map((srv, idx) => (
        <div key={srv.name} style={{ marginBottom: 20, color: "white" }}>
          <h2>{srv.name}</h2>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Mode</th>
                  <th>Major Alarms</th>
                  <th>Minor Alarms</th>
                  <th>Control Network</th>
                  <th>Processor Ethernet</th>
                  <th>PE Priority</th>
                  <th>Server Hardware</th>
                  <th>Processes</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{srv.tableData["ID"]}</td>
                  <td>{srv.tableData["Mode"]}</td>
                  <td>{srv.tableData["Major Alarms"]}</td>
                  <td>{srv.tableData["Minor Alarms"]}</td>
                  <td>{srv.tableData["Control Network"]}</td>
                  <td>{srv.tableData["Processor Ethernet"]}</td>
                  <td>{srv.tableData["PE Priority"]}</td>
                  <td>{srv.tableData["Server Hardware"]}</td>
                  <td>{srv.tableData["Processes"]}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ))}
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