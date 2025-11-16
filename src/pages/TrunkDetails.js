import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "../App.css";

export default function TrunkDetails() {
  const { product } = useParams();
  const navigate = useNavigate();

  const [dialogOpen, setDialogOpen] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState({});
  const [acknowledged, setAcknowledged] = useState({});
  const [alerts, setAlerts] = useState({});
  const [filter, setFilter] = useState("");

  const [isExecuting, setIsExecuting] = useState(false);
  const abortControllerRef = useRef(null);

  // new states
  const [loading, setLoading] = useState(false);
  const [tableData, setTableData] = useState([]);
  const [statusTrunkNumber, setStatusTrunkNumber] = useState("");

  const [columns, setColumns] = useState([]);
  const [excelPath, setExcelPath] = useState(null);


  const [progress, setProgress] = useState(0);

  const isRunningRef = useRef(false);




  // 🔴 New: Track which cards should blink (status-based alerts)
const [blinkingCards, setBlinkingCards] = useState(() => {
  const saved = sessionStorage.getItem(`blinkingCards:${product}`);
  return saved ? JSON.parse(saved) : {};
});


  // ✅ Helper: update and persist "Last Refreshed" timestamp
  const updateLastRefreshed = (title) => {
    try {
      const now = new Date().toISOString();
      const key = `lastRefreshed:${encodeURIComponent(product)}`;
      const updated = { ...(JSON.parse(sessionStorage.getItem(key)) || {}), [title]: now };
      sessionStorage.setItem(key, JSON.stringify(updated));
      setLastRefreshed(updated);
      console.log("✅ Last Refreshed updated:", key, updated);
    } catch (err) {
      console.error("❌ Failed to update lastRefreshed:", err);
    }
  };
  
  



  const cards = [
    { title: "list measurements trunk-group summary yesterday-peak" },
    { title: "monitor traffic trunk-groups" },
    { title: "list trunk-group" },
    { title: "status trunk" },
    { title: "list measurements outage-trunk last-hour" },
    { title: "status aesvcs cti-link" },
    { title: "list survivable-processor" },
    { title: "status media-gateway" },
    { title: "status media-processor all" },
    { title: "status aesvcs interface" },
    { title: "status aesvcs link" },
    { title: "status cdr-link" },




  ];





  // Persisted state load/save (unchanged)
  useEffect(() => {
    const stored = sessionStorage.getItem(`lastRefreshed:${encodeURIComponent(product)}`);

    if (stored) setLastRefreshed(JSON.parse(stored));
    
    
    const storedAck = sessionStorage.getItem(`acknowledged:${product}`);
    if (storedAck) setAcknowledged(JSON.parse(storedAck));
    const storedAlerts = sessionStorage.getItem(`alerts:${product}`);
    if (storedAlerts) setAlerts(JSON.parse(storedAlerts));

    const storedBlinking = sessionStorage.getItem(`alerts`);
    if (storedBlinking) setBlinkingCards(JSON.parse(storedBlinking));

  }, [product]);


  useEffect(() => {
    const key = `lastRefreshed:${encodeURIComponent(product)}`;
    const stored = sessionStorage.getItem(key);
    if (stored) setLastRefreshed(JSON.parse(stored));
  }, [product]);




  // useEffect(() => {
  //   sessionStorage.setItem(`lastRefreshed:${encodeURIComponent(product)}`, JSON.stringify(lastRefreshed));

  // }, [product, lastRefreshed]);
  
  // useEffect(() => {
  //   const key = encodeURIComponent(product);
  //   sessionStorage.setItem(`lastRefreshed:${encodeURIComponent(product)}`, JSON.stringify(lastRefreshed));
  //   sessionStorage.setItem(`acknowledged:${encodeURIComponent(product)}`, JSON.stringify(acknowledged));
  //   sessionStorage.setItem(`alerts:${encodeURIComponent(product)}`, JSON.stringify(alerts));
    
  // }, [product, lastRefreshed, acknowledged, alerts]);
  
  




  useEffect(() => {
    sessionStorage.setItem(`blinkingCards:${product}`, JSON.stringify(blinkingCards));
  }, [product, blinkingCards]);
  


  useEffect(() => {
    const interval = setInterval(() => {
      const stored = sessionStorage.getItem("alerts");
      if (stored) setBlinkingCards(JSON.parse(stored));
    }, 3000); // check every 3 seconds
    return () => clearInterval(interval);
  }, []);
  


  // keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (dialogOpen) {
        if (e.key === "Escape") {
          setDialogOpen(null);
        } else if (e.key === "Enter") {
          // Only trigger Enter when not executing
          if (!isExecuting) {
            if (dialogOpen === "status trunk") {
              // If status trunk, make sure a number exists
              handleCardClick(dialogOpen, "refresh", statusTrunkNumber);
            } else {
              handleCardClick(dialogOpen, "refresh");
            }
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [dialogOpen, isExecuting, statusTrunkNumber]);

  const handleCancelExecution = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsExecuting(false);
  };

  const handleSendAlert = async (title) => {
    const email = prompt("Enter recipient Gmail address:");
    const isValidGmail = /^[\w.+\-]+@gmail\.com$/.test(email);

    if (!isValidGmail) {
      alert("Please enter a valid Gmail address.");
      return;
    }

    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL_SMTP}send-alert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          subject: `ALERT: ${title} issue on ${product}`,
          body: `Critical alert detected in ${title} for product ${product}. Please investigate.`,
        }),
      });

      if (!res.ok) {
        const errorResponse = await res.json();
        throw new Error(errorResponse.error || "Unknown error");
      }

      const response = await res.json();
      alert(response.message || "Alert sent successfully!");
      setAlerts((prev) => ({ ...prev, [title]: true }));
    } catch (error) {
      console.error("Error sending alert:", error);
      alert("Failed to send alert. " + error.message);
    }
  };

  const criticalBlinkingCount = Object.keys(blinkingCards).filter(
    (title) => blinkingCards[title] && !acknowledged[title]
  ).length;
  
  const filteredCards = filter ? cards.filter((card) => card.title.toLowerCase().includes(filter.toLowerCase())) : cards;

  // Core: run commands (supports status trunk with trunkNumber)
  const handleCardClick = async (title, action, trunkNumber = null) => {
    if (isRunningRef.current) {
      console.warn("⚠️ Command already running, ignoring duplicate click:", title);
      return;
    }
    isRunningRef.current = true;
  



    const encodedProduct = encodeURIComponent(product);
    let encodedTitle = encodeURIComponent(title);
    const now = new Date().toLocaleString();

    if (title === "status trunk" && trunkNumber) {
      // append the trunk number to the nav title so TrunkCommandView can parse it
      encodedTitle = encodeURIComponent(`${title} ${trunkNumber}`);
    }

    // Abort previous controller and create a fresh one
    if (abortControllerRef.current) abortControllerRef.current.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (action === "refresh") {
      setIsExecuting(true);
      setProgress(0);
    
      // Gradual progress animation (simulated)
      const interval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) return prev; // cap before finish
          return prev + Math.random() * 5; // random small increments
        });
      }, 400);
    
      // Store interval handle to clear later
      abortControllerRef.current = { ...abortControllerRef.current, progressInterval: interval };
    }
    

    const executeCommand = async (url, body = null) => {
      try {
        const opts = { method: "POST", signal: controller.signal };
        if (body) {
          opts.headers = { "Content-Type": "application/json" };
          opts.body = JSON.stringify(body);
        }
        const res = await fetch(url, opts);
        if (!res.ok) {
          // try to extract backend error text
          let errText = "Script execution failed";
          try {
            const j = await res.json();
            errText = j.error || errText;
          } catch (_) {}
          throw new Error(errText);
        }
        // success -> mark last refreshed and navigate to view page

        //setLastRefreshed((prev) => ({ ...prev, [title]: now }));

        updateLastRefreshed(title);


        // ✅ For all except status trunk, navigate as before
        if (title !== "status trunk") {
          navigate(`/trunk-command/${encodedProduct}/${encodedTitle}`);
        }
        
      } catch (err) {
        if (err.name === "AbortError") {
          alert("Command execution canceled.");
        } else {
          alert("Error executing command: " + err.message);
        }
      } 
      finally {
        if (abortControllerRef.current?.progressInterval)
          clearInterval(abortControllerRef.current.progressInterval);
        setProgress(100);
        setTimeout(() => setProgress(0), 1000); // reset after done
        setIsExecuting(false);
        setLoading(false);
      }
      
    };

    try {
      setLoading(true);

      // if (title === "list measurements trunk-group summary yesterday-peak") {
      //   //await executeCommand(`${process.env.REACT_APP_API_URL}get-yesterday-peak-data`);
      //   navigate(`/trunk-command/${encodedProduct}/${encodedTitle}`);
      // } 


      if (title === "list measurements trunk-group summary yesterday-peak") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-yesterday-peak-data`);
      
        try {
          // Fetch latest data immediately after run
          const res = await fetch(`${process.env.REACT_APP_API_URL}get-yesterday-peak-data`);
          const json = await res.json();
      
          if (json?.data && Array.isArray(json.data)) {
            const hasAlert = json.data.some((row) => {
              const outSrvKey = Object.keys(row).find(
                (k) => k.trim().toLowerCase() === "out srv"
              );
              const atbKey = Object.keys(row).find(
                (k) => k.trim().toLowerCase() === "% atb"
              );
      
              const outSrvVal = parseFloat((row[outSrvKey] || "0").toString().trim());
              const atbVal = parseFloat((row[atbKey] || "0").toString().trim());
      
              return (outSrvVal && outSrvVal !== 0) || (atbVal && atbVal !== 0);
            });
      
            setBlinkingCards((prev) => ({
              ...prev,
              [title]: hasAlert && !acknowledged[title],
            }));
          }
        } catch (err) {
          console.error("Error updating blinking for yesterday-peak:", err);
        }
      }
      
      

      else if (title === "list trunk-group") {
        await executeCommand(`${process.env.REACT_APP_API_URL}run-list-trunk-group`);
      } else if (title === "monitor traffic trunk-groups") {
        await executeCommand(`${process.env.REACT_APP_API_URL}run-monitor-traffic-trunk-groups`);
      } 
      

      
      else if (title === "status trunk") {
        // 🔁 No user input, fully automatic
        await executeCommand(`${process.env.REACT_APP_API_URL}run-status-trunk`);
      
        // ✅ After backend finishes, navigate to trunk command viewer like others
        const encodedProduct = encodeURIComponent(product);
        const encodedTitle = encodeURIComponent(title);
        navigate(`/trunk-command/${encodedProduct}/${encodedTitle}`);
      }
      
      
      





      else if (title === "list measurements outage-trunk last-hour") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-list-measurements-outage-trunk-last-hour`);
      }

      else if (title === "status aesvcs cti-link") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-aesvcs-cti-link`);
      
        try {
          const res = await fetch(`${process.env.REACT_APP_API_URL}get-status-aesvcs-cti-link`);
          const json = await res.json();
      
          if (json?.data && Array.isArray(json.data)) {
            const hasAlert = json.data.some(
              (row) =>
                (row["Service State"] &&
                  row["Service State"].toLowerCase() !== "established") ||
                (row["Mnt Busy"] && row["Mnt Busy"].toLowerCase() !== "no")
            );
      
            setBlinkingCards((prev) => ({
              ...prev,
              [title]: hasAlert && !acknowledged[title],
            }));
          }
        } catch (err) {
          console.error("Error updating blinking for CTI link:", err);
        }
      }
      
      else if (title === "status aesvcs interface") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-aesvcs-interface`);
      
        try {
          const res = await fetch(`${process.env.REACT_APP_API_URL}get-status-aesvcs-interface`);
          const json = await res.json();
      
          if (json?.data && Array.isArray(json.data)) {
            const hasAlert = json.data.some(
              (row) =>
                (row["Status"] &&
                  row["Status"].toLowerCase() !== "listening") ||
                (row["Enabled?"] &&
                  row["Enabled?"].toLowerCase() !== "yes")
            );
      
            setBlinkingCards((prev) => ({
              ...prev,
              [title]: hasAlert && !acknowledged[title],
            }));
          }
        } catch (err) {
          console.error("Error updating blinking for interface:", err);
        }
      }
      



      else if (title === "list survivable-processor") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-list-survivable-processor-data`);
      
        try {
          const res = await fetch(`${process.env.REACT_APP_API_URL}get-list-survivable-processor-data`);
          const json = await res.json();
      
          if (json?.data && Array.isArray(json.data)) {
            const today = new Date();
      
            const hasAlert = json.data.some((row) => {
              const reg = (row["REG"] || "").trim().toLowerCase();
              const dateStr = (row["Translations Updated"] || "").trim();
      
              // Parse date safely (format like "05/11/2025" or "2025-11-05")
              let parsedDate = null;
              if (dateStr) {
                if (dateStr.includes("/")) {
                  // Try DD/MM/YYYY or MM/DD/YYYY formats
                  const parts = dateStr.split("/").map((p) => parseInt(p));
                  if (parts[2] && parts[0] <= 31) {
                    parsedDate = new Date(parts[2], parts[1] - 1, parts[0]); // DD/MM/YYYY
                  } else {
                    parsedDate = new Date(parts[0], parts[1] - 1, parts[2]); // fallback MM/DD/YYYY
                  }
                } else if (dateStr.includes("-")) {
                  parsedDate = new Date(dateStr);
                }
              }
      
              let dateTooOld = false;
              if (parsedDate && !isNaN(parsedDate)) {
                const diffMs = today - parsedDate;
                const diffDays = diffMs / (1000 * 60 * 60 * 24);
                dateTooOld = diffDays > 2; // 🔴 older than 2 days
              }
      
              return reg !== "y" || dateTooOld;
            });
      
            setBlinkingCards((prev) => ({
              ...prev,
              [title]: hasAlert && !acknowledged[title],
            }));
          }
        } catch (err) {
          console.error("Error updating blinking for survivable processor:", err);
        }
      }





      else if (title === "status cdr-link") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-cdr-link`);
      
        try {
          const res = await fetch(`${process.env.REACT_APP_API_URL}get-status-cdr-link`);
          const json = await res.json();
      
          if (json?.data && Array.isArray(json.data)) {
            const hasAlert = json.data.some((row) => {
              const linkState = (row["Link State"] || "").trim().toLowerCase();
              const bufferFullRaw = (row["CDR buffer % full"] || "").toString().trim();
      
              // parse % full to number safely
              let bufferFull = parseFloat(bufferFullRaw.replace("%", ""));
              if (isNaN(bufferFull)) bufferFull = 0;
      
              // 🔴 trigger blink if link down or buffer > 90%
              return linkState !== "up" || bufferFull > 90;
            });
      
            setBlinkingCards((prev) => ({
              ...prev,
              [title]: hasAlert && !acknowledged[title],
            }));
          }
        } catch (err) {
          console.error("Error updating blinking for status cdr-link:", err);
        }
      }


      

      else if (title === "status media-gateway") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-media-gateway`);
      
        try {
          const res = await fetch(`${process.env.REACT_APP_API_URL}get-status-media-gateway`);
          const json = await res.json();
      
          if (json?.data && Array.isArray(json.data)) {
            const hasAlert = json.data.some((row) => {
              const lk = (row["LK"] || "").trim().toLowerCase();
              const mj = parseInt(row["MJ"] || "0", 10);
              const mn = parseInt(row["MN"] || "0", 10);
              return lk !== "up" || mj !== 0 || mn !== 0;
            });
      
            setBlinkingCards((prev) => ({
              ...prev,
              [title]: hasAlert && !acknowledged[title],
            }));
          }
        } catch (err) {
          console.error("Error updating blinking for status media-gateway:", err);
        }
      }
      
      
      



      
      else if (title === "status media-processor all") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-media-processor-all`);
      }


      else if (title === "status aesvcs link") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-aesvcs-link`);
      }

      else if (title === "status cdr-link") {
        await executeCommand(`${process.env.REACT_APP_API_URL}get-status-cdr-link`);
      }

      else {
        navigate(`/trunk-details/${encodedProduct}/${encodedTitle}`);
      }
    } finally {
      setDialogOpen(null);
      isRunningRef.current = false;

    }
  };

  // helper to fetch yesterday-peak output into the table in this page (keeps compatibility)
  const handleRunYesterdayPeak = async () => {
    try {
      setLoading(true);
      setTableData([]);
  
      // ✅ Call only ONE endpoint
      const res = await fetch(`${process.env.REACT_APP_API_URL}get-yesterday-peak-data`);
      const json = await res.json();
  
      if (json.error) {
        alert("Error: " + json.error);
        return;
      }
  
      // ✅ Handle the returned structured data
      if (json.data && Array.isArray(json.data)) {
        setTableData(json.data);
        setExcelPath(json.excel_path || null);
        setColumns(json.columns || []);
      } else {
        alert("Unexpected response format from backend.");
      }
    } catch (err) {
      console.error(err);
      alert("Error executing or loading data");
    } finally {
      setLoading(false);
    }
  };
  

  return (
    <div className="app-container">
      {/* Top bar */}
      <div className="top-bar">
        <button className="home-button" onClick={() => navigate("/")}>🏠</button>
        <button className="refresh-button" onClick={() => navigate("/command-history")}>📜 View Command Logs</button>
      </div>
  
      <h1 className="dashboard-title">{decodeURIComponent(product)} – Trunk Details</h1>
  
      {/* KPI Summary */}
      <div className="summary-grid">
        <div className="summary-card">
          <h3>Commands</h3>
          <p>{cards.length}</p>
        </div>
        <div className="summary-card critical">
          <h3>Critical</h3>
          <p>{criticalBlinkingCount}</p>
        </div>
      </div>
  
      {/* Filter */}
      <div className="monitor-controls">
        <input
          type="text"
          placeholder="Filter cards by name..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
  
      {/* Cards */}
      <div className="widget-grid">
        {filteredCards.map((card, idx) => {
          const isBlinking = blinkingCards[card.title] && !acknowledged[card.title];
          return (
            <div
              key={idx}
              className={`widget-card ${isBlinking ? "blinking critical" : ""}`}
              onClick={() => setDialogOpen(card.title)}
              style={{ cursor: "pointer" }}
            >
              <h3>{card.title}</h3>






  
              {isBlinking && (
  <div
    style={{
      marginTop: "10px",
      display: "flex",
      justifyContent: "space-between",
      gap: "12px",
    }}
  >
    <button
      className="fancy-button alert-button"
      onClick={(e) => {
        e.stopPropagation();
        handleSendAlert(card.title);
      }}
      disabled={alerts[card.title]}
    >
      {alerts[card.title] ? "✅ Alert Sent" : "📧 Send Alert"}
    </button>

    <button
      className="fancy-button ack-button"
      onClick={(e) => {
        e.stopPropagation();
        setAcknowledged((prev) => ({ ...prev, [card.title]: true }));
      }}
    >
      {acknowledged[card.title] ? "✅ Acknowledged" : "✔ Acknowledge"}
    </button>
  </div>
)}








  
              <div
                style={{
                  marginTop: "14px",
                  backgroundColor: "#374151",
                  padding: "6px 10px",
                  borderRadius: "6px",
                  fontSize: "0.85rem",
                  fontWeight: "500",
                  color: "#f9fafb",
                }}
              >
Last Refreshed: {lastRefreshed[card.title]
  ? new Date(lastRefreshed[card.title]).toLocaleString()
  : "Never"}

              </div>
            </div>
          );
        })}
      </div>
  
      {loading && (
        <div
          style={{
            marginTop: "20px",
            color: "#60a5fa",
            fontWeight: "bold",
          }}
        >
          Fetching data and generating report... ⏳
        </div>
      )}
  
      {/* Table output */}
      {tableData.length > 0 && (
        <div style={{ marginTop: "20px", overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                {Object.keys(tableData[0]).map((key) => (
                  <th key={key}>{key}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableData.map((row, idx) => (
                <tr key={idx}>
                  {Object.values(row).map((val, i) => (
                    <td key={i}>{val}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
  
      {/* Dialog */}
      {dialogOpen && (
        <div className="dialog-overlay">
          <div className="dialog-box">
            <button
              className="dialog-close"
              onClick={() => setDialogOpen(null)}
              disabled={isExecuting}
              style={{ opacity: isExecuting ? 0.4 : 1 }}
            >
              ✖
            </button>
            <h2 className="dialog-title">{dialogOpen}</h2>
  
            {!isExecuting ? (
              <div className="dialog-actions">
                {dialogOpen === "status trunk" ? (
                  <div style={{ display: "flex", gap: 12 }}>
          <button
            className="dialog-btn refresh-btn"
            onClick={(e) => {
              e.stopPropagation();
              handleCardClick(dialogOpen, "refresh");
            }}
          >
            Refresh & View
          </button>

            
          <button
            className="dialog-btn view-btn"
            onClick={(e) => {
              e.stopPropagation(); // ✅ prevent bubbling
              if (isRunningRef.current) return; // ✅ avoid rapid double-clicks
              isRunningRef.current = true;

              try {
                sessionStorage.setItem("viewOnlyMode", "true");
                const encodedProduct = encodeURIComponent(product);
                const encodedTitle = encodeURIComponent(dialogOpen);
                navigate(`/trunk-command/${encodedProduct}/${encodedTitle}`);
              } finally {
                setDialogOpen(null);
                isRunningRef.current = false;
              }
            }}
          >
            View
          </button>

  
          <button
  className="dialog-btn"
  onClick={(e) => {
    e.stopPropagation();  // ✅ Prevents click bubbling to parent
    if (isRunningRef.current) return;  // ✅ Ignore if command running
    setDialogOpen(null);  // ✅ Cleanly close dialog
  }}
>
  Cancel
</button>

                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 12 }}>
                              <button
            className="dialog-btn refresh-btn"
            onClick={(e) => {
              e.stopPropagation();
              handleCardClick(dialogOpen, "refresh");
            }}
          >
            Refresh & View
          </button>
  

          <button
            className="dialog-btn view-btn"
            onClick={(e) => {
              e.stopPropagation(); // ✅ prevent bubbling
              if (isRunningRef.current) return; // ✅ avoid rapid double-clicks
              isRunningRef.current = true;

              try {
                sessionStorage.setItem("viewOnlyMode", "true");
                const encodedProduct = encodeURIComponent(product);
                const encodedTitle = encodeURIComponent(dialogOpen);
                navigate(`/trunk-command/${encodedProduct}/${encodedTitle}`);
              } finally {
                setDialogOpen(null);
                isRunningRef.current = false;
              }
            }}
          >
            View
          </button>


  
          <button
  className="dialog-btn"
  onClick={(e) => {
    e.stopPropagation();  // ✅ Prevents click bubbling to parent
    if (isRunningRef.current) return;  // ✅ Ignore if command running
    setDialogOpen(null);  // ✅ Cleanly close dialog
  }}
>
  Cancel
</button>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ marginTop: "20px", width: "100%", textAlign: "center" }}>
                <div
                  className="loading-spinner"
                  style={{ margin: "0 auto 12px" }}
                ></div>
                <p
                  style={{
                    color: "#9ca3af",
                    fontSize: "0.95rem",
                    marginBottom: "10px",
                  }}
                >
                  Executing command, please wait...
                </p>
  
                {/* ✅ Progress Bar */}
                <div
                  style={{
                    height: "8px",
                    width: "80%",
                    background: "#1f2937",
                    borderRadius: "6px",
                    margin: "0 auto 14px",
                    overflow: "hidden",
                    boxShadow: "inset 0 0 3px rgba(0,0,0,0.3)",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${progress}%`,
                      background:
                        progress < 100
                          ? "linear-gradient(90deg, #3b82f6, #60a5fa)"
                          : "linear-gradient(90deg, #22c55e, #4ade80)",
                      transition: "width 0.4s ease",
                    }}
                  ></div>
                </div>
  
                <button
                  className="dialog-btn refresh-btn"
                  style={{ backgroundColor: "#ef4444", marginTop: "6px" }}
                  onClick={handleCancelExecution}
                >
                  ✖ Cancel Execution
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}  
