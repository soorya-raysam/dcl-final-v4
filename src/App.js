import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import TableView from "./pages/TableView";
import ProductDashboard from "./pages/ProductDashboard";
import SectionDetails from "./pages/SectionDetails";
import CertificateDetails from "./components/CertificateDetails";
import TrunkDetails from "./pages/TrunkDetails";
// import TrunkMonitorTable from "./pages/TrunkMonitorTable";
import TrunkGroupTable from "./pages/TrunkGroupTable";
import RegionDashboard from "./pages/RegionDashboard";
import TrunkCommandView from "./pages/TrunkCommandView";
import CommandHistory from "./pages/CommandHistory";


function App() {
  console.log("env: ", process.env.REACT_APP_API_URL);
  
  return (
    <Router>
      <Routes>
        {/* Home page with tabular layout */}
        <Route path="/" element={<TableView />} />

        {/* Product dashboard card layout */}
        <Route path="/region/:product" element={<RegionDashboard />} />
        <Route path="/dashboard/:product" element={<ProductDashboard />} />
        

        <Route path="/dashboard/:product" element={<ProductDashboard />} />
        <Route path="/details/:product/Certificates" element={<CertificateDetails />} />
        <Route path="/trunk-details/:product" element={<TrunkDetails />} />
{/* <Route path="/trunk-details/:product/:title" element={<TrunkDetails />} /> */}
<Route path="/trunk-command/:product/:title" element={<TrunkCommandView />} />

<Route path="/command-history" element={<CommandHistory />} />



        {/* <Route
              path="/trunk-details/:product/:section"
              element={<div style={{ padding: "40px", color: "#fff" }}>Trunk Detail Page - Coming Soon</div>}/> */}


               {/* <Route
  path="/trunk-details/:product/list trunk-group"
  element={<TrunkGroupTable />}
/> */}

        {/* <Route path="/trunk-details/:product/:title" element={<TrunkMonitorTable />} /> */}
 
        
        <Route path="/" element={<TableView />} />



        {/* Specific detail view for a section under a product */}
        <Route path="/details/:product/:section" element={<SectionDetails />} />
      </Routes>
    </Router>
  );
}

export default App;
