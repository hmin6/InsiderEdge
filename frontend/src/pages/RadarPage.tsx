import { SignalAvailability } from "../components/SignalAvailability";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchRadar, usingResearchMocks } from "../api/client";
import { useResource } from '../hooks/useResource';
import { rankRadar, numeric, type RadarSortKey } from '../components/ResearchStates';
import {
  AppShell,
  PageContainer,
  ProductHeader,
  PanelSkeleton,
  StateMessage,
} from "../components";

const sortOptions: { key: RadarSortKey; label: string }[] = [
  { key: 'default', label: 'Default (Ranked Priority)' },
  { key: 'company', label: 'Company (A to Z)' },
  { key: 'status', label: 'Status Completeness' },
  { key: 'anomaly', label: 'Anomaly Score (High to Low)' },
  { key: 'activity', label: 'Activity Score (High to Low)' },
  { key: 'dislocation', label: 'Dislocation Score (High to Low)' },
  { key: 'model_prob', label: 'Model Probability (High to Low)' },
  { key: 'priority', label: 'Research Priority Score (High to Low)' },
];
export default function RadarPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<RadarSortKey>('default');
  const [direction, setDirection] = useState<'asc' | 'desc'>('desc');
  const [sortOpen, setSortOpen] = useState(false);
  const sortContainer = useRef<HTMLDivElement>(null);
  const sortTrigger = useRef<HTMLButtonElement>(null);
  const sortMenu = useRef<HTMLDivElement>(null);
  const resource = useResource('radar', fetchRadar);
  const { loading, error, retry } = resource;
  const data = rankRadar(resource.data?.items || []);
  const filteredData = rankRadar(data, { query, sortKey, direction });

  useEffect(() => {
    if (!sortOpen) return;
    sortMenu.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    const dismissOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !sortContainer.current?.contains(event.target)) setSortOpen(false);
    };
    const dismissEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setSortOpen(false);
        sortTrigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', dismissOutside);
    document.addEventListener('keydown', dismissEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside);
      document.removeEventListener('keydown', dismissEscape);
    };
  }, [sortOpen]);

  function navigateSortMenu(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Tab') { setSortOpen(false); return; }
    const options = Array.from(sortMenu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') || []);
    const index = options.indexOf(document.activeElement as HTMLButtonElement);
    let next: number;
    if (event.key === 'ArrowDown') next = (index + 1) % options.length;
    else if (event.key === 'ArrowUp') next = (index - 1 + options.length) % options.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = options.length - 1;
    else return;
    event.preventDefault();
    options[next]?.focus();
  }

  function searchCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanTicker = query.trim().toUpperCase();
    if (cleanTicker) navigate('/company/' + encodeURIComponent(cleanTicker));
  }

  const shellNavigation = [{ label: "Radar", href: "/", current: true }];

  if (loading) {
    return (
      <AppShell navigation={shellNavigation}>
        <PageContainer>
          <ProductHeader title="Market Dislocation Radar" />
          <PanelSkeleton label="Loading Radar..." rows={5} />
        </PageContainer>
      </AppShell>
    );
  }

  if (error) {
    return (
      <AppShell navigation={shellNavigation}>
        <PageContainer>
          <ProductHeader title="Market Dislocation Radar" />
          <StateMessage kind="error" title="Unable to load Radar" actions={<button className="ie-button" onClick={retry}>Retry Radar</button>}>
            Failed to fetch current signals.
          </StateMessage>
        </PageContainer>
      </AppShell>
    );
  }

return (
    <AppShell navigation={shellNavigation}>
      <PageContainer className="ie-reveal">
        <div className="ie-radar-header-bar">
          <ProductHeader
            eyebrow="Research Queue"
            title="Market Dislocation Radar"
            description="High score indicates research priority, not an investment recommendation."
          />

          <form
            className="ie-radar-quick-search"
            role="search"
            aria-label="Ticker search"
            onSubmit={searchCompany}
          >
            <div className="ie-radar-search-controls">
              <input
                id="radar-ticker-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search ticker or name..."
                aria-label="Search ticker or company name"
                autoComplete="off"
                spellCheck={false}
              />
              <button
                className="ie-button ie-button--primary"
                type="submit"
                disabled={!query.trim()}
              >
                Search
              </button>
              <div className="ie-radar-sort" ref={sortContainer}>
                <button
                  className="ie-button"
                  type="button"
                  id="radar-sort-trigger"
                  ref={sortTrigger}
                  aria-haspopup="menu"
                  aria-expanded={sortOpen}
                  aria-controls={sortOpen ? 'radar-sort-menu' : undefined}
                  onClick={() => setSortOpen((open) => !open)}
                  onKeyDown={(event) => {
                    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                      event.preventDefault();
                      setSortOpen(true);
                    }
                  }}
                >Sort</button>
                {sortOpen && (
                  <div className="ie-radar-sort-menu" id="radar-sort-menu" role="menu"
                    aria-labelledby="radar-sort-trigger" ref={sortMenu} onKeyDown={navigateSortMenu}>
                    {sortOptions.map((option) => (
                      <button key={option.key} type="button" role="menuitemradio" tabIndex={-1}
                        aria-checked={sortKey === option.key}
                        onClick={() => {
                          setSortKey(option.key);
                          setDirection(option.key === 'company' ? 'asc' : 'desc');
                          setSortOpen(false);
                          sortTrigger.current?.focus();
                        }}>
                        <span aria-hidden="true">{sortKey === option.key ? '●' : '○'}</span>
                        {option.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {sortKey !== 'default' && <button className="ie-button" type="button"
                aria-label={`Sort direction: ${direction === 'asc' ? 'ascending' : 'descending'}`}
                onClick={() => setDirection(value => value === 'asc' ? 'desc' : 'asc')}>
                {direction === 'asc' ? 'Ascending' : 'Descending'}
              </button>}
            </div>
            {query.trim() && (
              <span
                className="ie-radar-filter-count"
                role="status"
                aria-live="polite"
              >
                {filteredData.length}/{data.length} found
              </span>
            )}
          </form>
        </div>

        {usingResearchMocks && (
          <p className="ie-muted">
            Development mock data · Not measured research results.
          </p>
        )}

        {!data.length && (
          <StateMessage
            title="No research events available"
            actions={
              <button className="ie-button" onClick={retry}>
                Refresh Radar
              </button>
            }
          >
            No ranked signals are available. Please check again later.
          </StateMessage>
        )}

        <div
          className="ie-panel ie-table-scroll ie-radar-region"
          tabIndex={0}
          aria-label="Research priority table"
        >
          <table className="ie-table ie-radar-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Signal Summary</th>
                <th>Status</th>
                <th className="ie-number">Anomaly</th>
                <th className="ie-number">Activity</th>
                <th className="ie-number">Dislocation</th>
                <th className="ie-number">Model probability</th>
                <th className="ie-number ie-priority-column">
                  Research priority score
                </th>
              </tr>
            </thead>
            <tbody>
              {data.length > 0 && !filteredData.length && (
                <tr>
                  <td colSpan={8}>
                    No matching research events. Clear the filter to see the
                    full queue, or search a ticker to open its research page.
                  </td>
                </tr>
              )}
              {filteredData.map((item) => (
                <tr key={`${item.ticker}-${item.public_event_day}`}>
                  <td>
                    <Link
                      to={`/company/${item.ticker}`}
                      style={{ textDecoration: "none" }}
                    >
                      <strong>{item.ticker}</strong>
                      <br />
                      <span className="ie-muted">{item.company_name}</span>
                    </Link>
                  </td>
                  <td>{item.insider_signal_summary || "—"}</td>
                  <td>
                    <SignalAvailability evidence={item} />
                  </td>
                  <td className="ie-number">
                    {numeric(item.anomaly_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.activity_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.dislocation_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.ml_outperformance_probability, true)}
                  </td>
                  <td className="ie-number ie-priority-column">
                    <strong>{numeric(item.insider_edge_score)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PageContainer>
    </AppShell>
  );
}
