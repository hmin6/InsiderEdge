import { BrowserRouter, Routes, Route, Link } from "react-router-dom";

// Placeholder components to validate routing for Issue #19
const RadarPage = () => (
  <div style={{ padding: "2rem" }}>
    <h1>Market Dislocation Radar</h1>
    <Link to="/company/AAPL">View AAPL Mock Data</Link>
  </div>
);

const CompanyPage = () => (
  <div style={{ padding: "2rem" }}>
    <h1>Company Research Page</h1>
    <Link to="/">Back to Radar</Link>
  </div>
);

const ErrorFallback = () => (
  <div style={{ padding: "2rem", color: "red" }}>
    <h2>Application Error</h2>
    <p>Something went wrong loading the UI.</p>
  </div>
);

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RadarPage />} />
        <Route path="/company/:ticker" element={<CompanyPage />} />
        <Route path="*" element={<ErrorFallback />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
