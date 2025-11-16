import React, { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "../App.css";

export default function ProductDashboard() {
  const { product } = useParams();
  const navigate = useNavigate();
  const hasInitialized = useRef(false);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [acknowledged, setAcknowledged] = useState(() => {
    const stored = localStorage.getItem("acknowledgedAlarms");
    return stored ? JSON.parse(stored) : false;
  });
  const [alarmSeverity, setAlarmSeverity] = useState("Normal");
  const [criticalAlarmActive, setCriticalAlarmActive] = useState(false);
  const [criticalCertActive, setCriticalCertActive] = useState(false);

  const [refreshTimer, setRefreshTimer] = useState(30);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(() => {
    const saved = localStorage.getItem("autoRefreshEnabled");
    return saved ? JSON.parse(saved) : false;
  });
  const [countdown, setCountdown] = useState(() => {
    const saved = localStorage.getItem("globalCountdown");
    return saved ? parseInt(saved) : 0;
  });

  // --- Fetch Data ---
  const fetchData = () => {
    fetch(`${process.env.REACT_APP_API_URL}get-live-health-data`)
      .then((res) => res.json())
      .then((json) => {
        setData(json);
        setLoading(false);
        analyzeSeverity(json);
      })
      .catch((err) => {
        console.error("Failed to fetch dashboard data", err);
        setError("Failed to load dashboard data");
        setLoading(false);
      });
  };

  const handleManualRefresh = () => {
    fetchData(); // Manual refresh should NOT reset auto refresh countdown
  };

  useEffect(() => {
    fetchData();
  }, [product]);

  // --- Countdown sync with localStorage ---
  useEffect(() => {
    const handleStorage = (e) => {
      if (e.key === "globalCountdown") {
        const value = parseInt(e.newValue);
        if (!isNaN(value)) setCountdown(value);
      }
      if (e.key === "autoRefreshEnabled") {
        setAutoRefreshEnabled(JSON.parse(e.newValue));
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  // --- Severity logic ---
  const analyzeSeverity = (json) => {
    const alarmsText = (json?.alarms || "").toLowerCase();
    const serverText = (json?.server_status || "").toLowerCase();

    let severity = "Normal";
    let criticalActive = false;

    if (
      alarmsText.includes("critical") ||
      serverText.includes("critical") ||
      serverText.includes("mode: critical")
    ) {
      severity = "Critical";
      criticalActive = true;
    } else if (
      (alarmsText.includes("major alarms: yes") ||
        serverText.includes("major alarms: yes")) &&
      !alarmsText.includes("major alarms: no")
    ) {
      severity = "Major";
    } else if (
      (alarmsText.includes("minor alarms: yes") ||
        serverText.includes("minor alarms: yes")) &&
      !alarmsText.includes("minor alarms: no")
    ) {
      severity = "Minor";
    }

    setAlarmSeverity(severity);
    setCriticalAlarmActive(criticalActive);
    setCriticalCertActive(false);
  };

  const handleAcknowledge = () => {
    setAcknowledged(true);
    localStorage.setItem("acknowledgedAlarms", JSON.stringify(true));
    window.dispatchEvent(new Event("storage"));
  };

  const getStatusColor = (status) => {
    switch (status) {
      case "Normal":
        return "normal";
      case "Minor":
        return "warning";
      case "Major":
        return "major";
      case "Critical":
        return "critical";
      default:
        return "unknown";
    }
  };

  const cards = [
    {
      title: "System Uptime",
      value: data?.system_uptime || "N/A",
      status: "Normal",
      path: "Uptime",
    },
    {
      title: "Disk Utilisation (df -h)",
      value: data?.disk_utilisation?.["df -h"] ? "Available" : "N/A",
      status: "Normal",
      path: "Disk Utilisation (df -h)",
    },
    {
      title: "Disk Utilisation (df -k)",
      value: data?.disk_utilisation?.["df -k"] ? "Available" : "N/A",
      status: "Normal",
      path: "Disk Utilisation (df -k)",
    },
    {
      title: "Server Status",
      value: "View details",
      status: "Normal",
      path: "Server Status",
    },
    {
      title: "Backup",
      value: "View details",
      status: "Normal",
      path: "Backup",
    },
    {
      title: "Alarms",
      value: alarmSeverity,
      status: alarmSeverity,
      path: "Alarms",
      blinking:
        !acknowledged &&
        (alarmSeverity === "Critical" || alarmSeverity === "Major"),
    },
  ];

  const handleCardClick = (section) => {
    navigate(`/details/${encodeURIComponent(product)}/${encodeURIComponent(section)}`);
  };

  const formatTime = (secs) => {
    const d = Math.floor(secs / 86400);
    const h = Math.floor((secs % 86400) / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${d ? d + "d " : ""}${h ? h + "h " : ""}${m ? m + "m " : ""}${s}s`;
  };

  if (loading)
    return <div className="loading">Loading dashboard data...</div>;

  return (
    <div className="app-container">
      {/* --- Header Bar --- */}
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
          style={{
            padding: "8px 18px",
            fontSize: "1rem",
            borderRadius: "8px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            cursor: "pointer",
          }}
          onClick={handleManualRefresh}
        >
          🔄 Refresh
        </button>

        {/* Auto Refresh Indicator */}
        <div
          style={{
            background: autoRefreshEnabled ? "#16a34a" : "#ef4444",
            padding: "6px 14px",
            borderRadius: "8px",
            color: "#fff",
            fontSize: "0.9rem",
            fontWeight: "500",
          }}
        >
          Auto Refresh: {autoRefreshEnabled ? "Enabled" : "Disabled"}
        </div>

        {autoRefreshEnabled && (
          <div style={{ color: "#9ca3af", fontSize: "0.9rem" }}>
            Next refresh in <strong>{formatTime(countdown)}</strong>
          </div>
        )}
      </div>

      {/* --- Breadcrumb --- */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1rem",
        }}
      >
        <div style={{ fontSize: "0.95rem", color: "#9ca3af" }}>
          <span
            style={{ cursor: "pointer", textDecoration: "underline" }}
            onClick={() => navigate("/")}
          >
            🏠 Home
          </span>{" "}
          / {decodeURIComponent(product)} / <strong>Dashboard</strong>
        </div>
      </div>

      <h1 className="dashboard-title">
        {decodeURIComponent(product)} Dashboard
      </h1>

      {/* --- KPI Summary --- */}
      <div className="kpi-grid">
        <div
          className={`kpi-card ${
            criticalAlarmActive && !acknowledged ? "blinking-red" : ""
          }`}
        >
          <h3>Critical Alarms</h3>
          <p style={{ color: criticalAlarmActive ? "#f87171" : "#9ca3af" }}>
            {criticalAlarmActive ? "1" : "0"}
          </p>
        </div>

        <div className={`kpi-card ${criticalCertActive ? "blinking-red" : ""}`}>
          <h3>Critical Certificates</h3>
          <p style={{ color: criticalCertActive ? "#f87171" : "#9ca3af" }}>
            {criticalCertActive ? "1" : "0"}
          </p>
        </div>
      </div>

      {/* --- Cards --- */}
      <div className="widget-grid">
        {cards.map((card, idx) => {
          const isBlinking = card.blinking && !acknowledged;
          return (
            <div
              key={idx}
              className={`widget-card ${
                isBlinking
                  ? card.status === "Critical"
                    ? "blinking-red"
                    : "blinking-purple"
                  : ""
              }`}
              onClick={() => handleCardClick(card.path)}
            >
              <h2>{card.title}</h2>
              <div className={`status-indicator ${getStatusColor(card.status)}`}>
                {card.value}
              </div>

              {card.title === "Alarms" && isBlinking && (
                <div style={{ marginTop: "12px" }}>
                  <button
                    className="fancy-button ack-button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAcknowledge();
                    }}
                  >
                    ✔ Acknowledge
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
