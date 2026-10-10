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

function radarScore(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? numeric(value) : value.toFixed(2);
}

type SortField = 'default' | 'company' | 'status' | 'anomaly' | 'activity' | 'dislocation' | 'model_prob' | 'priority';
type SortDirection = 'none' | 'asc' | 'desc';
type FlyoutSide = 'right' | 'left' | 'below';
const sortOptions: { key: Exclude<SortField, 'default'>; label: string }[] = [
  { key: 'company', label: 'Company' },
  { key: 'status', label: 'Status' },
  { key: 'anomaly', label: 'Anomaly' },
  { key: 'activity', label: 'Activity' },
  { key: 'dislocation', label: 'Dislocation' },
  { key: 'model_prob', label: 'Model Probability' },
  { key: 'priority', label: 'Research Priority Score' },
];
function flyoutSide(left: number, right: number, viewport: number): FlyoutSide {
  if (viewport <= 600) return 'below';
  if (right + 276 <= viewport - 8) return 'right';
  return left >= 284 ? 'left' : 'below';
}
function sortLabel(field: SortField, direction: SortDirection) {
  if (direction === 'none') return '—';
  if (field === 'company') return direction === 'asc' ? 'A-Z' : 'Z-A';
  if (field === 'status') return direction === 'desc' ? 'Complete first' : 'Insufficient first';
  return direction === 'desc' ? 'High-Low' : 'Low-High';
}
function directionOptions(field: SortField): { direction: Exclude<SortDirection, 'none'>; label: string }[] {
  return [
    ...(field === 'company' ? [
      { direction: 'asc' as const, label: 'A → Z (Ascending)' },
      { direction: 'desc' as const, label: 'Z → A (Descending)' },
    ] : field === 'status' ? [
      { direction: 'desc' as const, label: 'Complete first' },
      { direction: 'asc' as const, label: 'Insufficient first' },
    ] : [
      { direction: 'desc' as const, label: 'High → Low (Descending)' },
      { direction: 'asc' as const, label: 'Low → High (Ascending)' },
    ]),
  ];
}
const metricFields = {
  anomaly: 'anomaly_score', activity: 'activity_score', dislocation: 'dislocation_score',
  model_prob: 'ml_outperformance_probability', priority: 'insider_edge_score',
} as const;

function compareRadar(a: RadarItem, b: RadarItem, key: SortField, direction: SortDirection) {
  if (key === 'default' || direction === 'none') return 0;
  const multiplier = direction === 'asc' ? 1 : -1;
  if (key === 'company') return multiplier * a.ticker.localeCompare(b.ticker, 'en', { sensitivity: 'base' });
  if (key === 'status') {
    const completeness = (status: string) => status === 'complete' ? 2 : status === 'partial' ? 1 : 0;
    return multiplier * (completeness(a.score_status) - completeness(b.score_status));
  }
  const left = a[metricFields[key]], right = b[metricFields[key]];
  const leftValid = typeof left === 'number' && Number.isFinite(left);
  const rightValid = typeof right === 'number' && Number.isFinite(right);
  if (!leftValid) return rightValid ? 1 : 0;
  if (!rightValid) return -1;
  return multiplier * (left - right);
}

export default function RadarPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ field: SortField; direction: SortDirection }>({ field: 'default', direction: 'none' });
  const [openField, setOpenField] = useState<Exclude<SortField, 'default'> | null>(null);
  const [flyoutPosition, setFlyoutPosition] = useState<{ side: FlyoutSide; top: number }>({ side: 'right', top: 0 });
  const focusFlyout = useRef(false);
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
  ).sort((a, b) => compareRadar(a, b, sort.field, sort.direction));

  function closeSort() {
    setSortOpen(false);
    setOpenField(null);
  }
  function openFlyout(field: Exclude<SortField, 'default'>, row: Element, focus = false) {
    const bounds = row.getBoundingClientRect();
    setFlyoutPosition({ side: flyoutSide(bounds.left, bounds.right, window.innerWidth),
      top: Math.max(8 - bounds.top, Math.min(0, window.innerHeight - bounds.top - 158)) });
    focusFlyout.current = focus;
    setOpenField(field);
    if (focus && openField === field) {
      const selected = row.querySelector<HTMLButtonElement>('[aria-checked="true"]');
      (selected || row.querySelector<HTMLButtonElement>('[role="menuitemradio"]'))?.focus();
    }
  }

  useEffect(() => {
    if (openField && focusFlyout.current) {
      const selected = sortMenu.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"][aria-checked="true"]');
      (selected || sortMenu.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"]'))?.focus();
      focusFlyout.current = false;
    }
  }, [openField]);

  useEffect(() => {
    if (!sortOpen) return;
    sortMenu.current?.querySelector<HTMLButtonElement>('[data-sort-trigger]')?.focus();
    const dismissOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !sortContainer.current?.contains(event.target)) closeSort();
    };
    const dismissEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeSort();
        sortTrigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', dismissOutside);
    document.addEventListener('keydown', dismissEscape);
    window.addEventListener('resize', closeSort);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside);
      document.removeEventListener('keydown', dismissEscape);
      window.removeEventListener('resize', closeSort);
    };
  }, [sortOpen]);

  function navigateSortMenu(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Tab') { closeSort(); return; }
    const submenu = (event.target as HTMLElement).closest('.ie-radar-sort-flyout');
    if (submenu && event.key === 'ArrowLeft') {
      event.preventDefault();
      setOpenField(null);
      sortMenu.current?.querySelector<HTMLButtonElement>(`[data-sort-trigger="${openField}"]`)?.focus();
      return;
    }
    const options = Array.from(submenu
      ? submenu.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')
      : sortMenu.current?.querySelectorAll<HTMLButtonElement>('[data-sort-trigger], [data-sort-reset]') || []);
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
        <p className="ie-eyebrow">Research Queue</p>
        <div className="ie-radar-header-bar">
          <h1>Market Dislocation Radar</h1>

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
                  onClick={() => { setSortOpen((open) => !open); setOpenField(null); }}
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
                    {sortOptions.map((option) => {
                      const direction = sort.field === option.key ? sort.direction : 'none';
                      return <div className="ie-radar-sort-row" key={option.key} role="none"
                        onMouseEnter={(event) => openFlyout(option.key, event.currentTarget)}>
                        <button type="button" role="menuitem" tabIndex={-1}
                          id={`sort-field-${option.key}`} data-sort-trigger={option.key}
                          aria-haspopup="menu" aria-expanded={openField === option.key}
                          aria-controls={openField === option.key ? `sort-options-${option.key}` : undefined}
                          data-active={openField === option.key}
                          onFocus={() => { if (openField !== option.key) setOpenField(null); }}
                          onClick={(event) => openFlyout(option.key, event.currentTarget.parentElement!, true)}
                          onKeyDown={(event) => {
                            if (event.key === 'ArrowRight') {
                              event.preventDefault();
                              openFlyout(option.key, event.currentTarget.parentElement!, true);
                            }
                          }}>
                          <span className="ie-radar-sort-label">{option.label}</span>
                          <span className="ie-radar-sort-badge">{sortLabel(option.key, direction)}</span>
                        </button>
                        {openField === option.key && <div className="ie-radar-sort-flyout" role="menu"
                          data-side={flyoutPosition.side} style={flyoutPosition.side === 'below' ? undefined : { top: flyoutPosition.top }}
                          id={`sort-options-${option.key}`} aria-labelledby={`sort-field-${option.key}`}>
                          {directionOptions(option.key).map((choice) => <button type="button" key={choice.direction}
                            role="menuitemradio" tabIndex={-1} aria-checked={direction === choice.direction}
                            onClick={() => {
                              setSort({ field: option.key, direction: choice.direction });
                              closeSort();
                              sortTrigger.current?.focus();
                            }}>{choice.label}</button>)}
                        </div>}
                      </div>;
                    })}
                    <button className="ie-radar-sort-reset" type="button" role="menuitem" tabIndex={-1}
                      data-sort-reset onMouseEnter={() => setOpenField(null)} onFocus={() => setOpenField(null)}
                      onClick={() => {
                        setSort({ field: 'default', direction: 'none' });
                        closeSort();
                        sortTrigger.current?.focus();
                      }}>Default</button>
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
        <p className="ie-description ie-radar-description">
          High score indicates research priority, not an investment recommendation.
        </p>

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
