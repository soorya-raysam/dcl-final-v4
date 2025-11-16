import React, { useEffect, useState } from "react";
import "../App.css";

export default function CommandHistory() {
  const [logs, setLogs] = useState([]);
  const [filteredLogs, setFilteredLogs] = useState([]);
  const [commandList, setCommandList] = useState([]);
  const [selectedCommand, setSelectedCommand] = useState("All");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLogs();
  }, []);


  // ✅ Listen for dashboard updates (triggered from TableView.js)
useEffect(() => {
  const handleLogsUpdated = () => fetchLogs();
  window.addEventListener("commandLogsUpdated", handleLogsUpdated);
  return () => window.removeEventListener("commandLogsUpdated", handleLogsUpdated);
}, []);


  const fetchLogs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL}get-command-logs`);
      const json = await res.json();
      
      if (json.error) {
        console.error("Error fetching logs:", json.error);
        setLogs([]);
        setFilteredLogs([]);
        setCommandList([]);
      } else {
        const logsData = json.logs || []; // ✅ backend sends { logs: [...] }
        setLogs(logsData);
        setFilteredLogs(logsData);
        const distinct = [
          ...new Set(logsData.map((l) => l.command_name).filter(Boolean)),
        ];
        setCommandList(["All", ...distinct]);
      }
      
    } catch (err) {
      console.error("Fetch logs failed:", err);
      setLogs([]);
      setFilteredLogs([]);
    } finally {
      setLoading(false);
    }
  };

  const downloadHistory = () => {
    window.open(`${process.env.REACT_APP_API_URL}download-command-logs`, "_blank");
  };

  const downloadExcel = (excelPath) => {
    if (!excelPath) return alert("No excel available for this run.");
    const filename = excelPath.split("/").pop();
    window.open(
      `${process.env.REACT_APP_API_URL}download-excel/${encodeURIComponent(filename)}`,
      "_blank"
    );
  };

  const handleFilterChange = (e) => {
    const cmd = e.target.value;
    setSelectedCommand(cmd);
    if (cmd === "All") {
      setFilteredLogs(logs);
    } else {
      setFilteredLogs(logs.filter((l) => l.command_name === cmd));
    }
  };

  return (
    <div className="app-container">
      <h1 className="dashboard-title">Command History</h1>

      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <label
            htmlFor="commandFilter"
            style={{
              fontSize: "0.95rem",
              color: "#f9fafb",
              fontWeight: 500,
            }}
          >
            Filter by Command:
          </label>
          <select
            id="commandFilter"
            value={selectedCommand}
            onChange={handleFilterChange}
            style={{
              backgroundColor: "#1f2937",
              color: "#f9fafb",
              border: "1px solid #374151",
              borderRadius: "8px",
              padding: "6px 12px",
              fontSize: "0.9rem",
              outline: "none",
              cursor: "pointer",
            }}
          >
            {commandList.map((cmd, idx) => (
              <option key={idx} value={cmd}>
                {cmd}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", gap: "10px" }}>
          <button className="fancy-button" onClick={fetchLogs}>
            🔄 Refresh
          </button>
          <button className="fancy-button" onClick={downloadHistory}>
            ⬇️ Download Logs Excel
          </button>
        </div>
      </div>

      {/* Logs Table */}
      {loading ? (
        <p className="loading">Loading logs...</p>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Command</th>
                <th>Status</th>
                <th>Executed At</th>
                <th>Output Summary</th>
                <th>Excel</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: "center", padding: 20 }}>
                    No logs found
                  </td>
                </tr>
              ) : (
                filteredLogs.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td style={{ maxWidth: 320, wordBreak: "break-word" }}>
                      {row.command_name}
                    </td>
                    <td
                      style={{
                        color:
                          row.status === "Success" ? "#10b981" : "#ef4444",
                      }}
                    >
                      {row.status}
                    </td>
                    <td>{row.executed_at}</td>
                    <td
                      style={{
                        maxWidth: 400,
                        wordBreak: "break-word",
                        color: "#e5e7eb",
                      }}
                    >
                      {row.output_summary || "-"}
                    </td>
                    <td>
                      {row.excel_path ? (
                        <button
                          className="fancy-button"
                          onClick={() => downloadExcel(row.excel_path)}
                        >
                          ⬇️ Download
                        </button>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
