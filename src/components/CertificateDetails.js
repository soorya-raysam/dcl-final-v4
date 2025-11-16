import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import "../App.css";

export default function CertificateDetails() {
  const { product } = useParams();
  const section = "Certificates";

  const [certs, setCerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/health_snapshot.json")
      .then((res) => res.json())
      .then((data) => {
        if (
          section?.toLowerCase() === "certificates" &&
          Array.isArray(data?.certificate?.details)
        ) {
          setCerts(data.certificate.details);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch certificate details", err);
        setError("Failed to load certificate data");
        setLoading(false);
      });
  }, [section]);

  return (
    <div className="app-container">
      <h1 className="dashboard-title">
        {decodeURIComponent(product)} – Certificate Details
      </h1>

      {loading && <p className="loading">Loading...</p>}
      {error && <p className="loading">{error}</p>}

      {!loading && !error && certs.length === 0 && (
        <p style={{ color: "white", textAlign: "center" }}>
          No certificate details found.
        </p>
      )}

      {!loading && !error && certs.length > 0 && (
        <div className="cert-grid">
          {certs.map((cert, idx) => {
            const isCritical = cert.status === "Critical";

            return (
              <div
                key={idx}
                className={`status-box ${
                  isCritical ? "critical blinking" : "normal"
                }`}
                style={{
                  minHeight: "160px",
                  border: "2px solid rgba(255,255,255,0.15)",
                  marginBottom: "24px",
                  padding: "20px",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
                  borderRadius: "12px",
                  background: isCritical
                    ? "#dc3545" // red background
                    : "rgba(255, 255, 255, 0.95)",
                  color: isCritical ? "#fff" : "#1f2937",
                }}
              >
                <h3>{cert.name}</h3>
                <hr style={{ margin: "10px 0", borderTop: "1px solid #ccc" }} />
                <p><strong>Status:</strong> {cert.status}</p>
                <p><strong>Expires On:</strong> {cert.expires_on}</p>
                <p><strong>Days Remaining:</strong> {cert.expires_in_days}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
