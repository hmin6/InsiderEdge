import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppShell, PageContainer, Panel, PanelSkeleton, ProductHeader, RoleBadge, ScoreStatusBadge, StateMessage, StatusBadge } from './components';
import './styles/index.css';

// Component preview only: no company fixtures, financial metrics, or page business logic.
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

createRoot(document.getElementById('root')!).render(<StrictMode><VisualSystemPreview /></StrictMode>);
