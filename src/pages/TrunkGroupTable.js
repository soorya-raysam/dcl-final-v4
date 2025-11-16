import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import "../App.css";

export default function TrunkGroupTable() {
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
    groupNo: idx + 1,
    tac: "",
    type: "",
    name: "",
    mem: "",
    tn: "",
    cor: "",
    cdr: "",
    meas: "",
    outDsp: "",
    queLen: ""
  }));

  const filteredRows = filter
    ? rows.filter((row) => row.groupNo.toString().includes(filter))
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
      <h2 className="dashboard-title">
        {decodeURIComponent(product)} – {decodeURIComponent(title)}
      </h2>

      <div className="monitor-controls">
        <input
          type="text"
          placeholder="Filter by Group Number "
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />

        <div className="legend">
          <strong>Legend:</strong> &nbsp;
          Grp No: Group Number, TAC: Access Code, COR: Class of Restriction, CDR: Call Detail Recording,
          Meas: Measurements, Out Dsp: Outgoing Display, Que Len: Queue Length
        </div>

        <div className="last-refreshed">
          Last Refreshed: <strong>{lastRefreshed}</strong>
        </div>
      </div>

      <table className="monitor-table">
        <thead>
          <tr>
            <th>Grp No</th>
            <th>TAC</th>
            <th>Group Type</th>
            <th>Group Name</th>
            <th>Mem</th>
            <th>TN</th>
            <th>COR</th>
            <th>CDR</th>
            <th>Meas</th>
            <th>Out Dsp</th>
            <th>Que Len</th>
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((row) => (
            <tr key={row.groupNo}>
              <td>{row.groupNo}</td>
              <td>{row.tac}</td>
              <td>{row.type}</td>
              <td>{row.name}</td>
              <td>{row.mem}</td>
              <td>{row.tn}</td>
              <td>{row.cor}</td>
              <td>{row.cdr}</td>
              <td>{row.meas}</td>
              <td>{row.outDsp}</td>
              <td>{row.queLen}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
