import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import "../App.css";

export default function TrunkMonitorTable() {
  const { product, title } = useParams();
  const [filter, setFilter] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState("Never");

  useEffect(() => {
    const key = `lastRefreshed:${product}`;
    const stored = sessionStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored);
      const ts = parsed[decodeURIComponent(title)];
      if (ts) setLastRefreshed(new Date(ts).toLocaleString());
    }
  }, [product, title]);

  const rows = new Array(5).fill(null).map((_, idx) => ({
    id: (idx+1)*3,
    s: "30",
    a: "0",
    q: "0",
    w: "0"
  }));

  const filteredRows = filter
    ? rows.filter((row) => row.id.toString().includes(filter))
    : rows;

  return (
    <div className="monitor-table-container">
      <div style={{ position: "absolute", top: 24, right: 32 }}>
        <button
          className="fancy-button"
          style={{ padding: "8px 18px", fontSize: "1rem", borderRadius: "8px", background: "#2563eb", color: "#fff", border: "none", cursor: "pointer" }}
          onClick={() => alert("Dummy refresh!")}
        >
          Refresh
        </button>
      </div>

    <button class="home-button">Dashboard</button>

      <h2 className="dashboard-title">
        {decodeURIComponent(product)} – {decodeURIComponent(title)}
      </h2>

      <div className="monitor-controls">
        <input
          type="text"
          placeholder="Filter by Group (#)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />

        <div className="legend">
          <strong>Legend:</strong> &nbsp;
          #: Group, S: Group size, A: Active members, Q: Q length, W: Calls waiting
        </div>

        <div className="last-refreshed">
          Last Refreshed: <strong>{lastRefreshed}</strong>
        </div>
      </div>

      <table className="monitor-table">
        <thead>
          <tr>
            <th>#</th>
            <th>S</th>
            <th>A</th>
            <th>Q</th>
            <th>W</th>
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((row) => (
            <tr key={row.id}>
              <td>{row.id}</td>
              <td>{row.s}</td>
              <td>{row.a}</td>
              <td>{row.q}</td>
              <td>{row.w}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
