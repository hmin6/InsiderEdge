import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { AppShell, PageContainer, Panel, PanelSkeleton, ProductHeader, RoleBadge, ScoreStatusBadge, StateMessage, StatusBadge } from './components';

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

function VisualSystemPreview() {
  return <AppShell navigation={[{ label: 'Visual system', href: '#preview', current: true }]} utility={<StatusBadge tone="info">Development preview</StatusBadge>}>
    <PageContainer id="preview">
      <ProductHeader eyebrow="InsiderEdge / Shared components" title="Research workspace" description="Reusable product components for Radar and Company Research pages. This preview contains no measured financial results." actions={<a className="ie-button ie-button--primary" href="#components">Explore components</a>} />
      <div className="ie-grid" id="components">
        <Panel title="Insider roles" description="Role categories supplied by the data layer.">
          <div className="ie-inline"><RoleBadge role="Executive" /><RoleBadge role="Director" /><RoleBadge role="Other" /></div>
        </Panel>
        <Panel title="Evidence status" description="Availability stays visible alongside research priority.">
          <div className="ie-stack"><div className="ie-inline"><ScoreStatusBadge status="complete" /><ScoreStatusBadge status="partial" /><ScoreStatusBadge status="insufficient_data" /></div><p className="ie-muted">A high InsiderEdge Score means higher research priority. It does not imply a trading recommendation.</p></div>
        </Panel>
        <Panel title="Shared interaction styles" description="Compact controls with visible keyboard focus."><div className="ie-inline"><button className="ie-button ie-button--primary" disabled>Unavailable action</button><a className="ie-button" href="#loading">Inspect loading states</a></div></Panel>
        <Panel title="No evidence available" description="Missing values remain explicit."><StateMessage title="Research data is not connected">Connect the page’s data source to display persisted evidence.</StateMessage></Panel>
        <div id="loading"><PanelSkeleton label="Example of a loading research panel" /></div>
      </div>
    </PageContainer>
  </AppShell>;
}

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
