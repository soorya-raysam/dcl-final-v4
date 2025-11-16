import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../App.css";
import { Settings } from "lucide-react"; // ⚙️ icon

// 🔍 Helper to check if any trunk card under Avaya CM is blinking
const getAvayaCMTrunkStatus = () => {
  try {
    const alerts = JSON.parse(sessionStorage.getItem("alerts") || "{}");
    const hasCritical = Object.keys(alerts).some((key) => alerts[key] === true);
    return hasCritical ? "Critical" : "Normal";
  } catch (err) {
    console.error("Error reading alerts from sessionStorage:", err);
    return "Normal";
  }
};

const getStatusClass = (status, blinking) => {
  if (!status) return "unknown";
  const s = status.toLowerCase();
  if (blinking && (s === "critical" || s === "major"))
    return `${s} ${s === "critical" ? "blinking-red" : "blinking-purple"}`;
  return s;
};

const capitalize = (str) => str.charAt(0).toUpperCase() + str.slice(1);

export default function TableView() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [showModal, setShowModal] = useState(false);

  // 🔧 NEW: SSH/IP Settings modal and expiry tracking
  const [showSettings, setShowSettings] = useState(false);
  const [ipAddress, setIpAddress] = useState(localStorage.getItem("ssh_ip") || "");
  const [password, setPassword] = useState(localStorage.getItem("ssh_password") || "");
  const [passwordSetAt, setPasswordSetAt] = useState(
    localStorage.getItem("passwordSetAt") ? new Date(localStorage.getItem("passwordSetAt")) : null
  );

  // 🔔 Track if any trunk command is critical
  const [isAvayaCMTrunkCritical, setIsAvayaCMTrunkCritical] = useState(false);

  const [acknowledged, setAcknowledged] = useState(() => {
    const stored = localStorage.getItem("acknowledgedAlarms");
    return stored ? JSON.parse(stored) : false;
  });

  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(() => {
    const saved = localStorage.getItem("autoRefreshEnabled");
    return saved ? JSON.parse(saved) : false;
  });

  const [refreshConfig, setRefreshConfig] = useState(() => {
    const saved = localStorage.getItem("refreshConfig");
    return saved
      ? JSON.parse(saved)
      : { days: 0, hours: 0, minutes: 0, seconds: 30 };
  });

  const [countdown, setCountdown] = useState(() => {
    return (
      refreshConfig.days * 86400 +
      refreshConfig.hours * 3600 +
      refreshConfig.minutes * 60 +
      refreshConfig.seconds
    );
  });



  const [hasLoadedOnce, setHasLoadedOnce] = useState(() =>
    sessionStorage.getItem("hasLoadedOnce") === "true"
  );
  

  // 🧠 Check password expiry logic
  const checkPasswordExpiry = () => {
    if (!passwordSetAt) return;
    const daysElapsed = Math.floor((Date.now() - passwordSetAt.getTime()) / (1000 * 60 * 60 * 24));
    const daysLeft = 30 - daysElapsed;

    if (daysLeft <= 0) {
      alert("⚠️ SSH password expired! Please re-enter in Settings.");
      setShowSettings(true);
    } else if (daysLeft <= 2) {
      alert(`🔔 SSH password will expire in ${daysLeft} day(s). Please update soon.`);
    }
  };

  useEffect(() => {
    checkPasswordExpiry();
  }, []);

  const handleSaveSettings = () => {
    if (!ipAddress || !password) {
      alert("Please fill out both IP address and password.");
      return;
    }
    localStorage.setItem("ssh_ip", ipAddress);
    localStorage.setItem("ssh_password", password);
    localStorage.setItem("passwordSetAt", new Date().toISOString());
    setPasswordSetAt(new Date());
    alert("✅ Connection settings saved successfully!");
    setShowSettings(false);
  };

  // --- Fetch Data ---
  const fetchData = async (forceRefresh = false) => {
    try {
      // 🧠 Step 1: Check cache
      const cached = sessionStorage.getItem("dashboardCache");
      const cachedTime = sessionStorage.getItem("dashboardCacheTime");
      const now = Date.now();
  
      // Cache expiry = 2 minutes
      const CACHE_DURATION = 2 * 60 * 1000;
  
      if (
        !forceRefresh &&
        cached &&
        cachedTime &&
        now - parseInt(cachedTime, 10) < CACHE_DURATION
      ) {
        console.log("⚡ Using cached dashboard data");
        setData(JSON.parse(cached));
        setLoading(false);
        return;
      }
  
      // 🧠 Step 2: Fetch from backend
      console.log("🔄 Fetching new dashboard data...");
      setRefreshing(true);
  
      const res = await fetch(`${process.env.REACT_APP_API_URL}get-live-health-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ip: localStorage.getItem("ssh_ip"),
          password: localStorage.getItem("ssh_password"),
        }),
      });
  
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date().toLocaleString());
  
      // 🧠 Step 3: Cache it
      sessionStorage.setItem("dashboardCache", JSON.stringify(json));
      sessionStorage.setItem("dashboardCacheTime", now.toString());
      sessionStorage.setItem("hasLoadedOnce", "true");
      setHasLoadedOnce(true);

    } catch (err) {
      console.error("❌ Fetch error:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };
  

  const handleManualRefresh = () => {
    fetchData(true); // independent of auto refresh
  };

  const resetCountdown = () => {
    const total =
      refreshConfig.days * 86400 +
      refreshConfig.hours * 3600 +
      refreshConfig.minutes * 60 +
      refreshConfig.seconds;
    setCountdown(total);
    localStorage.setItem("globalCountdown", total);
  };

  useEffect(() => {
    if (!autoRefreshEnabled) return;
    const interval = setInterval(() => {
      setCountdown((prev) => {
        const next = prev - 1;
        localStorage.setItem("globalCountdown", next);
        if (next <= 0) {
          fetchData(true);
          resetCountdown();
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [autoRefreshEnabled, refreshConfig]);

  useEffect(() => {
    const listener = (e) => {
      if (e.key === "globalCountdown") {
        const val = parseInt(e.newValue);
        if (!isNaN(val)) setCountdown(val);
      }
      if (e.key === "autoRefreshEnabled") {
        setAutoRefreshEnabled(JSON.parse(e.newValue));
      }
      if (e.key === "refreshConfig") {
        setRefreshConfig(JSON.parse(e.newValue));
      }
      if (e.key === "acknowledgedAlarms") {
        setAcknowledged(JSON.parse(e.newValue));
      }
    };
    window.addEventListener("storage", listener);
    return () => window.removeEventListener("storage", listener);
  }, []);









  useEffect(() => {
    const cached = sessionStorage.getItem("dashboardCache");
    const cachedTime = sessionStorage.getItem("dashboardCacheTime");
  
    if (!hasLoadedOnce && (!cached || !cachedTime)) {
      // First time: fetch fresh data
      console.log("🟢 First dashboard load — fetching data...");
      fetchData(false);
    } else {
      // Already loaded once: reuse cached data
      const cachedData = sessionStorage.getItem("dashboardCache");
      if (cachedData) {
        console.log("⚡ Restoring dashboard from cache — no backend call");
        setData(JSON.parse(cachedData));
        setLoading(false);
      }
    }
  }, [hasLoadedOnce]);
  











  useEffect(() => {
    localStorage.setItem("autoRefreshEnabled", JSON.stringify(autoRefreshEnabled));
    localStorage.setItem("refreshConfig", JSON.stringify(refreshConfig));
  }, [autoRefreshEnabled, refreshConfig]);

  const analyzeSeverity = (text) => {
    if (!text) return "Normal";
    const lower = text.toLowerCase();
    if (lower.includes("critical") && !lower.includes("no critical")) return "Critical";
    if (lower.includes("major alarms: yes") || lower.includes("major active")) return "Major";
    if (lower.includes("minor alarms: yes") || lower.includes("minor active")) return "Minor";
    if (lower.includes("warning")) return "Warning";
    return "Normal";
  };

  const getRowData = (product) => {
    if (!data) {
      return {
        uptime: "Normal",
        disk: "Normal",
        server_status: "Normal",
        backup: "Normal",
        alarms: "Normal",
        certificate: "Normal",
      };
    }
  
    return {
      uptime: analyzeSeverity(data?.system_uptime || "Normal"),
      disk: analyzeSeverity(JSON.stringify(data?.disk_utilisation || {})),
      server_status: analyzeSeverity(data?.server_status || "Normal"),
      backup: analyzeSeverity(data?.backup_status || "Normal"),
      alarms: analyzeSeverity(data?.alarms || "Normal"),
      certificate: "Normal",
    };
  };
  

  const products = [
    "Avaya Communication Manager (CM)",
    "Avaya Session Border Controller",
    "Avaya Session Manager",
    "Avaya Aura Device Services (AADS)",
    "Avaya Aura® Messaging (AAMS)",
    "Avaya IX Messaging",
  ];

  const trunkStatuses = [
    { product: "Avaya Communication Manager (CM)", status: "Normal" },
    { product: "Avaya Session Border Controller", status: "Normal" },
    { product: "Avaya Session Manager", status: "Normal" },
    { product: "Avaya Aura Device Services (AADS)", status: "Normal" },
    { product: "Avaya Aura® Messaging (AAMS)", status: "Warning" },
    { product: "Avaya IX Messaging", status: "Normal" },
  ];

  const formatTime = (secs) => {
    const d = Math.floor(secs / 86400);
    const h = Math.floor((secs % 86400) / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${d ? d + "d " : ""}${h ? h + "h " : ""}${m ? m + "m " : ""}${s}s`;
  };

  const handleConfigChange = (key, value) => {
    const val = parseInt(value) || 0;
    setRefreshConfig((prev) => ({ ...prev, [key]: val }));
  };

  const handleSetAutoRefresh = () => {
    setAutoRefreshEnabled(true);
    resetCountdown();
    localStorage.setItem("autoRefreshEnabled", JSON.stringify(true));
    localStorage.setItem("refreshConfig", JSON.stringify(refreshConfig));
    setShowModal(false);
  };

  const handleDisableAutoRefresh = () => {
    setAutoRefreshEnabled(false);
    localStorage.setItem("autoRefreshEnabled", JSON.stringify(false));
    setShowModal(false);
  };

  // 🔁 Watch trunk alerts
  useEffect(() => {
    const checkAlerts = () => {
      try {
        const alerts = JSON.parse(sessionStorage.getItem("alerts") || "{}");
        const hasCritical = Object.values(alerts).some((v) => v === true);
        setIsAvayaCMTrunkCritical(hasCritical);
      } catch (err) {
        console.error("Error reading alerts:", err);
        setIsAvayaCMTrunkCritical(false);
      }
    };
    checkAlerts();
    const interval = setInterval(checkAlerts, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading">Loading system dashboard...</div>;

  return (
    <div className="table-container">
      {/* --- Settings Icon --- */}
      <div
        style={{
          position: "absolute",
          top: 24,
          left: 32,
          cursor: "pointer",
          color: "#9ca3af",
        }}
        title="Connection Settings"
        onClick={() => setShowSettings(true)}
      >
        <Settings size={22} />
      </div>

      {/* --- Header --- */}
      <div
        style={{
          position: "absolute",
          top: 24,
          right: 32,
          display: "flex",
          alignItems: "center",
          gap: "15px",
        }}
      >
        <button
          className="fancy-button"
          onClick={handleManualRefresh}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing..." : "🔄 Refresh"}
        </button>

        <button
          className="fancy-button"
          style={{
            background: autoRefreshEnabled ? "#22c55e" : "#f87171",
          }}
          onClick={() => setShowModal(true)}
        >
          ⚙️ Auto Refresh: {autoRefreshEnabled ? "Enabled" : "Disabled"}
        </button>

        {autoRefreshEnabled && (
          <div style={{ color: "#9ca3af", fontSize: "0.9rem" }}>
            Next refresh in <strong>{formatTime(countdown)}</strong>
          </div>
        )}
      </div>

      <h1 className="dashboard-title">Avaya System Health Dashboard</h1>

      {lastUpdated && (
        <div style={{ textAlign: "center", color: "#9ca3af", marginBottom: "1rem" }}>
          ⏱️ Last Refreshed At: {lastUpdated}
        </div>
      )}

      {/* --- Main Table --- */}
      <table className="dashboard-table">
        <thead>
          <tr>
            <th>Product</th>
            <th>Uptime</th>
            <th>Disk Utilisation</th>
            <th>Server Status</th>
            <th>Backup</th>
            <th>Alarms</th>
            <th>Certificates</th>
          </tr>
        </thead>
        <tbody>
          {products.map((p, i) => {
            const row = getRowData(p);
            const isCM = p === "Avaya Communication Manager (CM)";
            return (
              <tr key={i}>
                <td
                  className="product-name"
                  onClick={
                    isCM
                      ? () => navigate(`/dashboard/${encodeURIComponent(p)}`)
                      : undefined
                  }
                  style={{
                    cursor: isCM ? "pointer" : "default",
                    textDecoration: isCM ? "underline" : "none",
                  }}
                >
                  {p}
                </td>

                {[
                  ["uptime", "Uptime"],
                  ["disk", "Disk Utilisation"],
                  ["server_status", "Server Status"],
                  ["backup", "Backup"],
                  ["alarms", "Alarms"],
                  ["certificate", "Certificates"],
                ].map(([key, label]) => {
                  const status = row[key];
                  const blinking =
                    !acknowledged && (status === "Critical" || status === "Major");
                  let targetSection = label;
                  if (label === "Disk Utilisation")
                    targetSection = "Disk Utilisation (df -h)";

                  return (
                    <td
                      key={key}
                      className={getStatusClass(status, blinking)}
                      style={{
                        textAlign: "center",
                        textDecoration: "underline",
                        cursor: "pointer",
                        fontWeight: "500",
                        padding: "10px",
                      }}
                      onClick={() =>
                        navigate(
                          `/details/${encodeURIComponent(p)}/${encodeURIComponent(
                            targetSection
                          )}`
                        )
                      }
                    >
                      {status}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>





      {/* --- Trunk Monitoring --- */}
      <h2 className="dashboard-title" style={{ marginTop: "60px" }}>
        Trunk Monitoring
      </h2>
      <table className="dashboard-table">
        <thead>
          <tr>
            <th>Product</th>
            <th>Trunk Status</th>
          </tr>
        </thead>
        <tbody>
          {trunkStatuses.map((t, i) => {
            let status = t.status;
            let blinking = false;
            if (t.product === "Avaya Communication Manager (CM)") {
              status = isAvayaCMTrunkCritical ? "Critical" : "Normal";
              blinking = isAvayaCMTrunkCritical;
            }
            return (
              <tr key={i}>
                <td
                  onClick={() =>
                    navigate(`/trunk-details/${encodeURIComponent(t.product)}`)
                  }
                  style={{
                    cursor: "pointer",
                    textDecoration: "underline",
                    fontWeight: "600",
                  }}
                >
                  {t.product}
                </td>
                <td
                  className={getStatusClass(status, blinking)}
                  style={{
                    textAlign: "center",
                    fontWeight: "600",
                    color: blinking ? "#fff" : "inherit",
                  }}
                >
                  {status}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* --- Auto Refresh Modal --- */}
      {showModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#1f2937",
              borderRadius: "12px",
              padding: "24px 30px",
              width: "440px",
              color: "#f9fafb",
              boxShadow: "0 0 12px rgba(0,0,0,0.5)",
            }}
          >
            <h2
              style={{
                textAlign: "center",
                color: "#f9fafb",
                fontSize: "1.25rem",
                fontWeight: "600",
                marginBottom: "1.5rem",
              }}
            >
              ⚙️ Auto Refresh Settings
            </h2>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                textAlign: "center",
                fontSize: "0.8rem",
                color: "#9ca3af",
                marginBottom: "6px",
              }}
            >
              <span>Days</span>
              <span>Hours</span>
              <span>Minutes</span>
              <span>Seconds</span>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: "8px",
                marginBottom: "1.5rem",
              }}
            >
              {["days", "hours", "minutes", "seconds"].map((key) => (
                <input
                  key={key}
                  type="number"
                  min="0"
                  value={refreshConfig[key]}
                  onChange={(e) => handleConfigChange(key, e.target.value)}
                  style={{
                    background: "#111827",
                    color: "#f9fafb",
                    border: "1px solid #374151",
                    borderRadius: "6px",
                    padding: "6px",
                    textAlign: "center",
                    fontSize: "0.85rem",
                    width: "100%",
                  }}
                />
              ))}
            </div>

            <div style={{ textAlign: "center", marginTop: "10px" }}>
              <button
                className="fancy-button"
                style={{
                  background: "#2563eb",
                  marginRight: "12px",
                  minWidth: "130px",
                  padding: "8px 12px",
                }}
                onClick={handleSetAutoRefresh}
              >
                ✅ Set Auto Refresh
              </button>
              <button
                className="fancy-button"
                style={{
                  background: "#ef4444",
                  minWidth: "130px",
                  padding: "8px 12px",
                }}
                onClick={handleDisableAutoRefresh}
              >
                ❌ Disable
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --- NEW: Connection Settings Modal --- */}
      {showSettings && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1001,
          }}
        >
          <div
            style={{
              background: "#1f2937",
              borderRadius: "12px",
              padding: "24px 30px",
              width: "400px",
              color: "#f9fafb",
            }}
          >
            <h2 style={{ textAlign: "center", marginBottom: "1rem" }}>
              ⚙️ Connection Settings
            </h2>
            <label>IP Address:</label>
            <input
              type="text"
              value={ipAddress}
              onChange={(e) => setIpAddress(e.target.value)}
              style={{
                width: "100%",
                marginBottom: "12px",
                background: "#111827",
                color: "#f9fafb",
                border: "1px solid #374151",
                borderRadius: "6px",
                padding: "8px",
              }}
            />
            <label>Password:</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: "100%",
                marginBottom: "12px",
                background: "#111827",
                color: "#f9fafb",
                border: "1px solid #374151",
                borderRadius: "6px",
                padding: "8px",
              }}
            />
            {passwordSetAt && (
              <div style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
                Password last set on: {passwordSetAt.toLocaleString()}
              </div>
            )}
            <div style={{ textAlign: "center", marginTop: "12px" }}>
              <button
                className="fancy-button"
                style={{ background: "#2563eb", marginRight: "10px" }}
                onClick={handleSaveSettings}
              >
                💾 Save Settings
              </button>
              <button
                className="fancy-button"
                style={{ background: "#6b7280" }}
                onClick={() => setShowSettings(false)}
              >
                ❌ Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
