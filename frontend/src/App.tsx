import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { AppShell, PageContainer, StateMessage, PanelBoundary } from './components';
import RadarPage from "./pages/RadarPage";
import CompanyPage from "./pages/CompanyPage";

const ErrorFallback = () => (
  <AppShell navigation={[{ label: 'Radar', href: '/' }]}><PageContainer><StateMessage title="Page not found" actions={<Link className="ie-button" to="/">Return to Radar</Link>}>This research page does not exist.</StateMessage></PageContainer></AppShell>
);

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PanelBoundary label="Radar"><RadarPage /></PanelBoundary>} />
        <Route path="/company/:ticker" element={<PanelBoundary label="Company research"><CompanyPage /></PanelBoundary>} />
        <Route path="*" element={<ErrorFallback />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;