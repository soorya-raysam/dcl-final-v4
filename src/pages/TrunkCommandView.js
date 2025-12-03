import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "../App.css";

export default function TrunkCommandView() {
  const { product, title } = useParams();
  const decodedProduct = decodeURIComponent(product);
  const decodedTitle = decodeURIComponent(title);
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [tableData, setTableData] = useState([]);
  const [error, setError] = useState(null);
  const [excelPath, setExcelPath] = useState(null);

  // add new state
  const [columns, setColumns] = useState([]);

  const [showCriticalOnly, setShowCriticalOnly] = useState(false);


  useEffect(() => {
    const fetchData = async () => {
      const viewOnly = sessionStorage.getItem("viewOnlyMode") === "true";
  
      // --------------------------
      // VIEW-ONLY MODE (NO REFRESH)
      // --------------------------
      if (viewOnly) {
        console.log("📄 View mode: loading last saved result");
  
        sessionStorage.setItem("viewOnlyMode", "false");
  
        const saved = sessionStorage.getItem(`latestData:${title}`);

  
        const json = saved ? JSON.parse(saved) : { data: [], columns: [] };
  
        setColumns(json.columns || (json.data?.length ? Object.keys(json.data[0]) : []));
        setTableData(json.data || []);
        setExcelPath(json.excel_path || null);
  
        setLoading(false);
        return; // ⛔ STOP — do NOT fetch from backend
      }
  
      // --------------------------
      // REFRESH MODE
      // --------------------------
  
      try {
        setLoading(true);
        let url = "";
  
        if (decodedTitle === "list measurements trunk-group summary yesterday-peak") {
          url = `${process.env.REACT_APP_API_URL}get-yesterday-peak-data`;
        } else if (decodedTitle === "list trunk-group") {
          url = `${process.env.REACT_APP_API_URL}get-list-trunk-group-data`;
        } else if (decodedTitle === "monitor traffic trunk-groups") {
          url = `${process.env.REACT_APP_API_URL}get-monitor-traffic-trunk-groups-data`;
        } else if (decodedTitle === "status trunk") {
          url = `${process.env.REACT_APP_API_URL}get-status-trunk-all-data`;
        } else if (decodedTitle.startsWith("status trunk")) {
          const parts = decodedTitle.split(" ");
          const trunk = parts.length >= 3 ? parts.slice(2).join(" ") : "";
          url = `${process.env.REACT_APP_API_URL}get-status-trunk-data?trunk=${encodeURIComponent(trunk)}`;
        } else if (decodedTitle === "list measurements outage-trunk last-hour") {
          url = `${process.env.REACT_APP_API_URL}get-list-measurements-outage-trunk-last-hour`;
        } else if (decodedTitle === "status aesvcs cti-link") {
          url = `${process.env.REACT_APP_API_URL}get-status-aesvcs-cti-link`;
        } else if (decodedTitle === "list survivable-processor") {
          url = `${process.env.REACT_APP_API_URL}get-list-survivable-processor-data`;
        } else if (decodedTitle === "status media-gateway") {
          url = `${process.env.REACT_APP_API_URL}get-status-media-gateway`;
        } else if (decodedTitle === "status media-processor all") {
          url = `${process.env.REACT_APP_API_URL}get-status-media-processor-all`;
        } else if (decodedTitle === "status aesvcs interface") {
          url = `${process.env.REACT_APP_API_URL}get-status-aesvcs-interface`;
        } else if (decodedTitle === "status aesvcs link") {
          url = `${process.env.REACT_APP_API_URL}get-status-aesvcs-link`;
        } else if (decodedTitle === "status cdr-link") {
          url = `${process.env.REACT_APP_API_URL}get-status-cdr-link`;
        } else {
          setError("Unknown command view");
          setLoading(false);
          return;
        }
  
        // FETCH OPTIONS (POST only for yesterday-peak)
        let fetchOptions = { method: "GET" };

        // ALL commands that run SAT need POST
        const satCommands = [
          "list measurements trunk-group summary yesterday-peak",
          "list trunk-group",
          "monitor traffic trunk-groups"
        ];
        
        if (satCommands.includes(decodedTitle)) {
          fetchOptions = {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ip: localStorage.getItem("ssh_ip"),
              password: localStorage.getItem("ssh_password")
            })
          };
        }
        
  
        const res = await fetch(url, fetchOptions);
        const json = await res.json();
  
        if (json.error) throw new Error(json.error);
  
        // -------------------------------------------------------
        // SAVE RESULT FOR FUTURE VIEW-ONLY MODE (THE FIX IS HERE!)
        // -------------------------------------------------------
        sessionStorage.setItem(`latestData:${decodedTitle}`, JSON.stringify(json));

        // -----------------------
// NEW: Compute persistent alert/blink state and save into sessionStorage "alerts"
// -----------------------

// helper: detect "no data" placeholder row
const isNoDataResult = (j) => {
  if (!j || !j.data) return true;
  if (!Array.isArray(j.data) || j.data.length === 0) return true;

  // if single row and first cell contains "no data" or all cells empty
  if (j.data.length === 1) {
    const row = j.data[0];
    const vals = Object.values(row).map(v => (v === null || v === undefined) ? "" : String(v).trim().toLowerCase());
    const allEmpty = vals.every(v => v === "");
    const containsNoData = vals.some(v => v.includes("no data") || v.includes("no rows") || v.includes("no records") || v.includes("no valid"));
    if (allEmpty || containsNoData) return true;
  }
  return false;
};

let hasAlert = false;
const noData = isNoDataResult(json);

if (!noData && json.data && Array.isArray(json.data)) {
  // Evaluate using the same command-specific rules you already have in the view:
  if (decodedTitle === "status trunk" || decodedTitle.startsWith("status trunk")) {
    hasAlert = json.data.some(row => {
      const state = (row["Service State"] || "").toLowerCase();
      return !state.includes("in-service");
    });
  }

  else if (decodedTitle === "status aesvcs interface") {
    hasAlert = json.data.some(row =>
      (row["Status"] && row["Status"].toLowerCase() !== "listening") ||
      (row["Enabled?"] && row["Enabled?"].toLowerCase() !== "yes")
    );
  }

  else if (decodedTitle === "status aesvcs cti-link") {
    hasAlert = json.data.some(row =>
      (row["Service State"] && row["Service State"].toLowerCase() !== "established") ||
      (row["Mnt Busy"] && row["Mnt Busy"].toLowerCase() !== "no")
    );
  }

  else if (decodedTitle === "list survivable-processor") {
    const today = new Date();
    hasAlert = json.data.some(row => {
      const reg = (row["REG"] || "").trim().toLowerCase();
      const dateStr = (row["Translations Updated"] || "").trim();
      let parsedDate = new Date(dateStr);
      if (isNaN(parsedDate)) {
        const parts = dateStr.split(/[/-]/).map((x) => parseInt(x));
        if (parts.length === 3) parsedDate = new Date(parts[2], parts[1] - 1, parts[0]);
      }
      let dateTooOld = false;
      if (!isNaN(parsedDate)) {
        const diffDays = (today - parsedDate) / (1000 * 60 * 60 * 24);
        dateTooOld = diffDays > 2;
      }
      return reg !== "y" || dateTooOld;
    });
  }

  else if (decodedTitle === "status cdr-link") {
    hasAlert = json.data.some(row => {
      const linkState = (row["Link State"] || "").trim().toLowerCase();
      const bufferFullRaw = (row["CDR buffer % full"] || "").toString().trim();
      let bufferFull = parseFloat(bufferFullRaw.replace("%", ""));
      if (isNaN(bufferFull)) bufferFull = 0;
      return linkState !== "up" || bufferFull > 90;
    });
  }

  else if (decodedTitle === "status media-gateway") {
    hasAlert = json.data.some(row => {
      const lk = (row["LK"] || "").trim().toLowerCase();
      const mj = parseInt(row["MJ"] || "0", 10);
      const mn = parseInt(row["MN"] || "0", 10);
      return lk !== "up" || mj !== 0 || mn !== 0;
    });
  }

  else if (decodedTitle === "list measurements trunk-group summary yesterday-peak") {
    hasAlert = json.data.some(row => {
      const outSrvKey = Object.keys(row).find(k => k.trim().toLowerCase() === "out srv");
      const atbKey = Object.keys(row).find(k => k.trim().toLowerCase() === "% atb");
      const outSrvVal = parseFloat((row[outSrvKey] || "0").toString().trim()) || 0;
      const atbVal = parseFloat((row[atbKey] || "0").toString().trim()) || 0;
      return outSrvVal !== 0 || atbVal !== 0;
    });
  }

} else {
  hasAlert = false; // No data = no alert
}

// Merge with global alerts map
try {
  const existing = JSON.parse(sessionStorage.getItem("alerts") || "{}");
  existing[decodedTitle] = !!hasAlert;
  sessionStorage.setItem("alerts", JSON.stringify(existing));
} catch (e) {
  console.warn("Could not persist alerts map:", e);
}








  
        // -----------------------
        // APPLY DATA TO STATE
        // -----------------------
        if (json.data && Array.isArray(json.data)) {
          setColumns(json.columns || (json.data.length ? Object.keys(json.data[0]) : []));
          setTableData(json.data);
          setExcelPath(json.excel_path || null);
        } else if (Array.isArray(json)) {
          setColumns(json.length ? Object.keys(json[0]) : []);
          setTableData(json);
        } else {
          throw new Error("Unexpected response format");
        }
  
        // --------------------------------------
        // ALERT DETECTION (unchanged, kept safe)
        // --------------------------------------
        const savedAlerts = sessionStorage.getItem("alerts");
        const alerts = savedAlerts ? JSON.parse(savedAlerts) : {};
  
        // your existing alert evaluation logic remains untouched...
  
        sessionStorage.setItem("alerts", JSON.stringify(alerts));
  
      } catch (err) {
        setError(err.message || String(err));
      } finally {
        setLoading(false);
      }
    };
  
    fetchData();
  }, [decodedTitle]);
  
  
  


// 🔴 Count how many rows would trigger alert (critical)
const criticalCount = tableData.reduce((count, row) => {
  let isAlert = false;

  if (decodedTitle === "status aesvcs interface") {
    isAlert =
      (row["Status"] && row["Status"].toLowerCase() !== "listening") ||
      (row["Enabled?"] && row["Enabled?"].toLowerCase() !== "yes");
  } else if (decodedTitle === "status aesvcs cti-link") {
    isAlert =
      (row["Service State"] &&
        row["Service State"].toLowerCase() !== "established") ||
      (row["Mnt Busy"] && row["Mnt Busy"].toLowerCase() !== "no");
  } else if (decodedTitle === "list survivable-processor") {
    const today = new Date();
    const reg = (row["REG"] || "").trim().toLowerCase();
    const dateStr = (row["Translations Updated"] || "").trim();
    let parsedDate = new Date(dateStr);
    if (isNaN(parsedDate)) {
      const parts = dateStr.split(/[/-]/).map((x) => parseInt(x));
      if (parts.length === 3)
        parsedDate = new Date(parts[2], parts[1] - 1, parts[0]);
    }
    let dateTooOld = false;
    if (!isNaN(parsedDate)) {
      const diffDays = (today - parsedDate) / (1000 * 60 * 60 * 24);
      dateTooOld = diffDays > 2;
    }
    isAlert = reg !== "y" || dateTooOld;
  } else if (decodedTitle === "status cdr-link") {
    const linkState = (row["Link State"] || "").trim().toLowerCase();
    const bufferFullRaw = (row["CDR buffer % full"] || "").toString().trim();
    let bufferFull = parseFloat(bufferFullRaw.replace("%", ""));
    if (isNaN(bufferFull)) bufferFull = 0;
    isAlert = linkState !== "up" || bufferFull > 90;
  } else if (decodedTitle === "status media-gateway") {
    const lk = (row["LK"] || "").trim().toLowerCase();
    const mj = parseInt(row["MJ"] || "0", 10);
    const mn = parseInt(row["MN"] || "0", 10);
    isAlert = lk !== "up" || mj !== 0 || mn !== 0;
  } else if (
    decodedTitle === "list measurements trunk-group summary yesterday-peak"
  ) {
    const outSrvKey = Object.keys(row).find(
      (k) => k.trim().toLowerCase() === "out srv"
    );
    const atbKey = Object.keys(row).find(
      (k) => k.trim().toLowerCase() === "% atb"
    );
    const outSrvVal = parseFloat((row[outSrvKey] || "0").toString().trim());
    const atbVal = parseFloat((row[atbKey] || "0").toString().trim());
    isAlert = (outSrvVal && outSrvVal !== 0) || (atbVal && atbVal !== 0);
  } else if (decodedTitle === "status trunk") {
    const state = (row["Service State"] || "").toLowerCase();
    isAlert = !state.includes("in-service");
  }

  return isAlert ? count + 1 : count;
}, 0);








  const downloadExcel = () => {
    if (!excelPath) return alert("No excel available for this run.");
    const filename = excelPath.split("/").pop();
    window.open(`${process.env.REACT_APP_API_URL}download-excel/${encodeURIComponent(filename)}`, "_blank");
  };

  return (
    <div className="app-container">
      <div className="top-bar">
        <button className="home-button" onClick={() => navigate("/")}>🏠</button>
      </div>

      <h1 className="dashboard-title">
        {decodedProduct} – {decodedTitle}
      </h1>

      {loading && <p className="loading">Fetching latest data...</p>}
      {error && <p className="loading error">{error}</p>}




      {!loading && !error && tableData.length > 0 && (
  <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
    <button
      className="fancy-button"
      style={{
        backgroundColor: showCriticalOnly ? "#f87171" : "#60a5fa",
        transition: "background-color 0.2s ease",
      }}
      onClick={() => setShowCriticalOnly((prev) => !prev)}
    >
      {showCriticalOnly
  ? "Show All Rows"
  : `🔍 Show Only Critical (${criticalCount})`}

    </button>
  </div>
)}













      {!loading && !error && tableData.length > 0 && (
        <div style={{ marginTop: "20px", overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
  {tableData
    // ✅ Filter rows if toggle is ON
    .filter((row) => {
      if (!showCriticalOnly) return true;

      let isAlert = false;
      if (decodedTitle === "status aesvcs interface") {
        isAlert =
          (row["Status"] &&
            row["Status"].toLowerCase() !== "listening") ||
          (row["Enabled?"] &&
            row["Enabled?"].toLowerCase() !== "yes");
      } else if (decodedTitle === "status aesvcs cti-link") {
        isAlert =
          (row["Service State"] &&
            row["Service State"].toLowerCase() !== "established") ||
          (row["Mnt Busy"] &&
            row["Mnt Busy"].toLowerCase() !== "no");
      } else if (decodedTitle === "list survivable-processor") {
        const today = new Date();
        const reg = (row["REG"] || "").trim().toLowerCase();
        const dateStr = (row["Translations Updated"] || "").trim();
        let parsedDate = new Date(dateStr);
        if (isNaN(parsedDate)) {
          const parts = dateStr.split(/[/-]/).map((x) => parseInt(x));
          if (parts.length === 3)
            parsedDate = new Date(parts[2], parts[1] - 1, parts[0]);
        }
        let dateTooOld = false;
        if (!isNaN(parsedDate)) {
          const diffDays = (today - parsedDate) / (1000 * 60 * 60 * 24);
          dateTooOld = diffDays > 2;
        }
        isAlert = reg !== "y" || dateTooOld;
      } else if (decodedTitle === "status cdr-link") {
        const linkState = (row["Link State"] || "")
          .trim()
          .toLowerCase();
        const bufferFullRaw = (row["CDR buffer % full"] || "")
          .toString()
          .trim();
        let bufferFull = parseFloat(bufferFullRaw.replace("%", ""));
        if (isNaN(bufferFull)) bufferFull = 0;
        isAlert = linkState !== "up" || bufferFull > 90;
      } else if (decodedTitle === "status media-gateway") {
        const lk = (row["LK"] || "").trim().toLowerCase();
        const mj = parseInt(row["MJ"] || "0", 10);
        const mn = parseInt(row["MN"] || "0", 10);
        isAlert = lk !== "up" || mj !== 0 || mn !== 0;
      } else if (decodedTitle === "list measurements trunk-group summary yesterday-peak") {
        const outSrvKey = Object.keys(row).find(
          (k) => k.trim().toLowerCase() === "out srv"
        );
        const atbKey = Object.keys(row).find(
          (k) => k.trim().toLowerCase() === "% atb"
        );
        const outSrvVal = parseFloat(
          (row[outSrvKey] || "0").toString().trim()
        );
        const atbVal = parseFloat(
          (row[atbKey] || "0").toString().trim()
        );
        isAlert =
          (outSrvVal && outSrvVal !== 0) || (atbVal && atbVal !== 0);
      } else if (decodedTitle === "status trunk") {
        const state = (row["Service State"] || "").toLowerCase();
        isAlert = !state.includes("in-service");
      }
      return isAlert;
    })
    // ✅ Keep your existing mapping exactly as is
    .map((row, idx) => {
      let isAlert = false;

      // 🧠 Command-specific alert rules (unchanged)
      if (decodedTitle === "status aesvcs interface") {
        isAlert =
          (row["Status"] &&
            row["Status"].toLowerCase() !== "listening") ||
          (row["Enabled?"] &&
            row["Enabled?"].toLowerCase() !== "yes");
      } else if (decodedTitle === "status aesvcs cti-link") {
        isAlert =
          (row["Service State"] &&
            row["Service State"].toLowerCase() !== "established") ||
          (row["Mnt Busy"] &&
            row["Mnt Busy"].toLowerCase() !== "no");
      } else if (decodedTitle === "list survivable-processor") {
        const today = new Date();
        const reg = (row["REG"] || "").trim().toLowerCase();
        const dateStr = (row["Translations Updated"] || "").trim();
        let parsedDate = new Date(dateStr);
        if (isNaN(parsedDate)) {
          const parts = dateStr.split(/[/-]/).map((x) => parseInt(x));
          if (parts.length === 3)
            parsedDate = new Date(parts[2], parts[1] - 1, parts[0]);
        }
        let dateTooOld = false;
        if (!isNaN(parsedDate)) {
          const diffDays = (today - parsedDate) / (1000 * 60 * 60 * 24);
          dateTooOld = diffDays > 2;
        }
        isAlert = reg !== "y" || dateTooOld;
      } else if (decodedTitle === "status cdr-link") {
        const linkState = (row["Link State"] || "")
          .trim()
          .toLowerCase();
        const bufferFullRaw = (row["CDR buffer % full"] || "")
          .toString()
          .trim();
        let bufferFull = parseFloat(bufferFullRaw.replace("%", ""));
        if (isNaN(bufferFull)) bufferFull = 0;
        isAlert = linkState !== "up" || bufferFull > 90;
      } else if (decodedTitle === "status media-gateway") {
        const lk = (row["LK"] || "").trim().toLowerCase();
        const mj = parseInt(row["MJ"] || "0", 10);
        const mn = parseInt(row["MN"] || "0", 10);
        isAlert = lk !== "up" || mj !== 0 || mn !== 0;
      } else if (decodedTitle === "list measurements trunk-group summary yesterday-peak") {
        const outSrvKey = Object.keys(row).find(
          (k) => k.trim().toLowerCase() === "out srv"
        );
        const atbKey = Object.keys(row).find(
          (k) => k.trim().toLowerCase() === "% atb"
        );
        const outSrvVal = parseFloat(
          (row[outSrvKey] || "0").toString().trim()
        );
        const atbVal = parseFloat(
          (row[atbKey] || "0").toString().trim()
        );
        isAlert =
          (outSrvVal && outSrvVal !== 0) || (atbVal && atbVal !== 0);
      } else if (decodedTitle === "status trunk") {
        const state = (row["Service State"] || "").toLowerCase();
        isAlert = !state.includes("in-service");
      }

      return (
        <tr
          key={idx}
          style={{
            backgroundColor: isAlert ? "#fb0000" : "transparent",
            color: isAlert ? "black" : "inherit",
            transition: "background-color 0.3s ease",
          }}
        >
          {columns.map((col) => (
            <td key={col}>{row[col]}</td>
          ))}
        </tr>
      );
    })}
</tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 18 }}>
        <button className="fancy-button" onClick={() => window.location.reload()}>
          🔄 Refresh
        </button>{" "}
        <button className="fancy-button" onClick={() => navigate("/")}>
          🏠 Home
        </button>{" "}
        <button
          className="fancy-button"
          onClick={downloadExcel}
          disabled={!excelPath}
        >
          ⬇️ Download Excel
        </button>
      </div>

      {!loading && !error && tableData.length === 0 && (
        <p className="loading">No data available.</p>
      )}
    </div>
  );
}
