import React from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PieChart, Pie, Cell, Tooltip, Legend } from "recharts";
import "../App.css";

export default function RegionDashboard() {
  const { product } = useParams();
  const navigate = useNavigate();

  const dataDomestic = [
    { name: "Normal", value: 12 },
    { name: "Warning", value: 3 },
    { name: "Critical", value: 2 }
  ];

  const dataInternational = [
    { name: "Normal", value: 8 },
    { name: "Warning", value: 5 },
    { name: "Critical", value: 1 }
  ];

  const COLORS = ["#22c55e", "#facc15", "#ef4444"];

  const handleCardClick = (region) => {
    if (region === "Domestic") {
      navigate(`/dashboard/${encodeURIComponent(product)}`);
    } else {
      navigate(`/region/${encodeURIComponent(product)}/international`);
    }
  };

  return (
    <div className="app-container">
      <h1 className="dashboard-title">
        {decodeURIComponent(product)} – Region Overview
      </h1>

      <div className="region-grid">
        {/* Domestic Card */}
        <div
          className="region-card"
          onClick={() => handleCardClick("Domestic")}
          style={{ cursor: "pointer" }}
        >
          <h2>Domestic</h2>
          <PieChart width={300} height={250}>
            <Pie
              data={dataDomestic}
              cx="50%"
              cy="50%"
              labelLine={false}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
            >
              {dataDomestic.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </div>

        {/* International Card */}
        <div
          className="region-card"
          onClick={() => handleCardClick("International")}
          style={{ cursor: "pointer" }}
        >
          <h2>International</h2>
          <PieChart width={300} height={250}>
            <Pie
              data={dataInternational}
              cx="50%"
              cy="50%"
              labelLine={false}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
            >
              {dataInternational.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </div>
      </div>
    </div>
  );
}
