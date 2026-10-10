import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { RadarItem } from '../types/api';
import { fetchRadar, usingResearchMocks } from "../api/client";
import { useResource } from '../hooks/useResource';
import { rankRadar, numeric } from '../components/ResearchStates';
import {
  AppShell,
  PageContainer,
  ProductHeader,
  ScoreStatusBadge,
  PanelSkeleton,
  StateMessage,
} from "../components";

function radarScore(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? numeric(value) : value.toFixed(2);
}

type SortKey = 'default' | 'company' | 'status' | 'anomaly' | 'activity' | 'dislocation' | 'model_prob' | 'priority';
const sortOptions: { key: SortKey; label: string }[] = [
  { key: 'default', label: 'Default (Ranked Priority)' },
  { key: 'company', label: 'Company (A to Z)' },
  { key: 'status', label: 'Status Completeness' },
  { key: 'anomaly', label: 'Anomaly Score (High to Low)' },
  { key: 'activity', label: 'Activity Score (High to Low)' },
  { key: 'dislocation', label: 'Dislocation Score (High to Low)' },
  { key: 'model_prob', label: 'Model Probability (High to Low)' },
  { key: 'priority', label: 'Research Priority Score (High to Low)' },
];
const metricFields = {
  anomaly: 'anomaly_score', activity: 'activity_score', dislocation: 'dislocation_score',
  model_prob: 'ml_outperformance_probability', priority: 'insider_edge_score',
} as const;

function compareRadar(a: RadarItem, b: RadarItem, key: SortKey) {
  if (key === 'default') return 0;
  if (key === 'company') return a.ticker.localeCompare(b.ticker, 'en', { sensitivity: 'base' });
  if (key === 'status') {
    const completeness = (status: string) => status === 'complete' ? 2 : status === 'partial' ? 1 : 0;
    return completeness(b.score_status) - completeness(a.score_status);
  }
  const left = a[metricFields[key]], right = b[metricFields[key]];
  const leftValid = typeof left === 'number' && Number.isFinite(left);
  const rightValid = typeof right === 'number' && Number.isFinite(right);
  if (!leftValid) return rightValid ? 1 : 0;
  if (!rightValid) return -1;
  return right - left;
}

export default function RadarPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('default');
  const [sortOpen, setSortOpen] = useState(false);
  const sortContainer = useRef<HTMLDivElement>(null);
  const sortTrigger = useRef<HTMLButtonElement>(null);
  const sortMenu = useRef<HTMLDivElement>(null);
  const resource = useResource('radar', fetchRadar);
  const { loading, error, retry } = resource;
  const data = rankRadar(resource.data?.items || []);
  const filter = query.trim().toLowerCase();
  const filteredData = data.filter((item) =>
    item.ticker.toLowerCase().includes(filter) || item.company_name.toLowerCase().includes(filter),
  ).sort((a, b) => compareRadar(a, b, sortKey));

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
                    <ScoreStatusBadge status={item.score_status} />
                  </td>
                  <td className="ie-number">
                    {radarScore(item.anomaly_score)}
                  </td>
                  <td className="ie-number">
                    {radarScore(item.activity_score)}
                  </td>
                  <td className="ie-number">
                    {radarScore(item.dislocation_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.ml_outperformance_probability, true)}
                  </td>
                  <td className="ie-number ie-priority-column">
                    <strong>{radarScore(item.insider_edge_score)}</strong>
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
