import { SignalAvailability } from "../components/SignalAvailability";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { Joyride as ReactJoyride, Step, TooltipRenderProps } from "react-joyride";
import { fetchRadar, usingResearchMocks } from "../api/client";
import { useResource } from "../hooks/useResource";
import { rankRadar, numeric } from "../components/ResearchStates";
import type { RadarItem } from "../types/api";
import {
  AppShell,
  PageContainer,
  ProductHeader,
  PanelSkeleton,
  StateMessage,
} from "../components";

// --- START OF TOUR GUIDE IMPLEMENTATION ---
const MascotTooltip = ({
  index,
  step,
  backProps,
  primaryProps,
  skipProps,
  tooltipProps,
  isLastStep,
}: TooltipRenderProps) => (
  <div
    {...tooltipProps}
    style={{
      display: "flex",
      alignItems: "center",
      backgroundColor: "var(--ie-panel)",
      padding: "20px",
      borderRadius: "16px",
      color: "var(--ie-text)",
      maxWidth: "450px",
      gap: "15px",
      boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
      border: "1px solid var(--ie-border)",
      backdropFilter: "blur(12px)",
    }}
  >
    <div style={{ flexShrink: 0 }}>
      <img
        src="/mascot.svg"
        alt="Agent Mascot"
        style={{ width: "70px", height: "70px" }}
      />
    </div>
    <div style={{ flexGrow: 1 }}>
      <div
        style={{ fontSize: "15px", marginBottom: "15px", lineHeight: "1.5" }}
      >
        {step.content}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
        <button
          {...skipProps}
          className="ie-button"
          style={{
            background: "transparent",
            border: "none",
            color: "var(--ie-muted)",
          }}
        >
          Skip
        </button>
        {index > 0 && (
          <button
            {...backProps}
            className="ie-button"
            style={{ background: "transparent", border: "none" }}
          >
            Back
          </button>
        )}
        <button {...primaryProps} className="ie-button ie-button--primary">
          {isLastStep ? "Got it!" : "Next"}
        </button>
      </div>
    </div>
  </div>
);

const tourSteps: Step[] = [
  {
    target: "body",
    placement: "center",
    content:
      "Welcome to InsiderEdge! I'm Edge, your quantitative research assistant. Let's look at the market radar.",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-table",
    content:
      "This is the research queue. It constantly scans the market for significant insider trading events and ranks them by their statistical edge.",
    placement: "top",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-sort",
    content:
      "You can sort the queue by different quantitative components, like Market Dislocation or Anomaly scores.",
    placement: "bottom",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-quick-search",
    content:
      "Looking for a specific stock? Search for any ticker here to pull up its full institutional research profile.",
    placement: "bottom",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-table tbody tr:first-child",
    content:
      "Click on any company in this list to dive into the deep quantitative metrics, ML predictions, and AI explanations for that event!",
    placement: "bottom",
    disableBeacon: true,
  },
];
// --- END OF TOUR GUIDE IMPLEMENTATION ---

type SortField =
  | "default"
  | "company"
  | "status"
  | "anomaly"
  | "activity"
  | "dislocation"
  | "model_prob"
  | "priority";
type SortDirection = "none" | "asc" | "desc";
const sortOptions: { key: Exclude<SortField, "default">; label: string }[] = [
  { key: "company", label: "Company" },
  { key: "status", label: "Status" },
  { key: "anomaly", label: "Anomaly" },
  { key: "activity", label: "Activity" },
  { key: "dislocation", label: "Dislocation" },
  { key: "model_prob", label: "Model Probability" },
  { key: "priority", label: "Research Priority Score" },
];

function calculateFlyoutCoords(
  rect: { right: number; top: number },
  viewportWidth: number,
  viewportHeight: number,
  panelWidth = 220,
  panelHeight = 110,
) {
  const edge = 12;
  const width = Math.min(panelWidth, Math.max(0, viewportWidth - edge * 2));
  const height = Math.min(panelHeight, Math.max(0, viewportHeight - edge * 2));
  return {
    left: Math.max(
      edge,
      Math.min(rect.right - 10, viewportWidth - width - edge),
    ),
    top: Math.max(edge, Math.min(rect.top, viewportHeight - height - edge)),
  };
}

function sortLabel(field: SortField, direction: SortDirection) {
  if (direction === "none") return "—";
  if (field === "company") return direction === "asc" ? "A-Z" : "Z-A";
  if (field === "status")
    return direction === "desc" ? "Complete first" : "Insufficient first";
  return direction === "desc" ? "High-Low" : "Low-High";
}

function directionOptions(
  field: SortField,
): { direction: Exclude<SortDirection, "none">; label: string }[] {
  return [
    ...(field === "company"
      ? [
          { direction: "asc" as const, label: "A → Z (Ascending)" },
          { direction: "desc" as const, label: "Z → A (Descending)" },
        ]
      : field === "status"
        ? [
            { direction: "desc" as const, label: "Complete first" },
            { direction: "asc" as const, label: "Insufficient first" },
          ]
        : [
            { direction: "desc" as const, label: "High → Low (Descending)" },
            { direction: "asc" as const, label: "Low → High (Ascending)" },
          ]),
  ];
}

const metricFields = {
  anomaly: "anomaly_score",
  activity: "activity_score",
  dislocation: "dislocation_score",
  model_prob: "ml_outperformance_probability",
  priority: "insider_edge_score",
} as const;

function compareRadar(
  a: RadarItem,
  b: RadarItem,
  key: SortField,
  direction: SortDirection,
) {
  if (key === "default" || direction === "none") return 0;
  const multiplier = direction === "asc" ? 1 : -1;
  if (key === "company")
    return (
      multiplier *
      a.ticker.localeCompare(b.ticker, "en", { sensitivity: "base" })
    );
  if (key === "status") {
    const completeness = (status: string) =>
      status === "complete" ? 2 : status === "partial" ? 1 : 0;
    return (
      multiplier * (completeness(a.score_status) - completeness(b.score_status))
    );
  }
  const left = a[metricFields[key]],
    right = b[metricFields[key]];
  const leftValid = typeof left === "number" && Number.isFinite(left);
  const rightValid = typeof right === "number" && Number.isFinite(right);
  if (!leftValid) return rightValid ? 1 : 0;
  if (!rightValid) return -1;
  return multiplier * (left - right);
}

export default function RadarPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{
    field: SortField;
    direction: SortDirection;
  }>({ field: "default", direction: "none" });
  const [openField, setOpenField] = useState<Exclude<
    SortField,
    "default"
  > | null>(null);
  const [flyoutPosition, setFlyoutPosition] = useState({ left: 12, top: 12 });
  const flyoutPanel = useRef<HTMLDivElement>(null);
  const closeAllTimerRef = useRef<number | null>(null);
  const focusFlyout = useRef(false);
  const [sortOpen, setSortOpen] = useState(false);
  const sortContainer = useRef<HTMLDivElement>(null);
  const sortTrigger = useRef<HTMLButtonElement>(null);
  const sortMenu = useRef<HTMLDivElement>(null);
  const resource = useResource("radar", fetchRadar);

  const [runTour, setRunTour] = useState(false);
  const [tourKey, setTourKey] = useState(0);

  const { loading, error, retry } = resource;
  const data = rankRadar(resource.data?.items || []);
  const filter = query.trim().toLowerCase();
  const filteredData = data
    .filter(
      (item) =>
        item.ticker.toLowerCase().includes(filter) ||
        item.company_name.toLowerCase().includes(filter),
    )
    .sort((a, b) => compareRadar(a, b, sort.field, sort.direction));

  useEffect(() => {
    const hasSeenRadarTour = localStorage.getItem("ie_has_seen_radar_tour");
    if (!hasSeenRadarTour && data.length > 0) {
      setRunTour(true);
    }
  }, [data.length]);

  const handleJoyrideCallback = (joyrideData: any) => {
    const { status } = joyrideData;
    if (["finished", "skipped"].includes(status)) {
      setRunTour(false);
      localStorage.setItem("ie_has_seen_radar_tour", "true");
    }
  };

  const startTourManually = () => {
    setTourKey((prev) => prev + 1);
    setRunTour(true);
  };

  function clearTimer() {
    if (closeAllTimerRef.current !== null) {
      window.clearTimeout(closeAllTimerRef.current);
      closeAllTimerRef.current = null;
    }
  }

  function closeSort() {
    clearTimer();
    setSortOpen(false);
    setOpenField(null);
  }

  function scheduleClose() {
    clearTimer();
    if (!sortOpen) return;
    closeAllTimerRef.current = window.setTimeout(() => {
      closeAllTimerRef.current = null;
      if (
        sortContainer.current?.contains(document.activeElement) ||
        flyoutPanel.current?.contains(document.activeElement)
      )
        sortTrigger.current?.focus();
      closeSort();
    }, 160);
  }

  function handleParentMouseLeave(event: ReactMouseEvent) {
    const related = event.relatedTarget;
    if (related instanceof Node && flyoutPanel.current?.contains(related)) {
      clearTimer();
      return;
    }
    scheduleClose();
  }

  function handleFlyoutMouseLeave(event: ReactMouseEvent) {
    const related = event.relatedTarget;
    const activeRow = sortMenu.current
      ?.querySelector(`[data-sort-trigger="${openField}"]`)
      ?.closest(".ie-radar-sort-row");
    if (related instanceof Node && activeRow?.contains(related)) {
      clearTimer();
      return;
    }
    if (related instanceof Node && sortContainer.current?.contains(related)) {
      clearTimer();
      const target =
        related instanceof Element ? related : related.parentElement;
      if (!target?.closest(".ie-radar-sort-row")) setOpenField(null);
    } else scheduleClose();
  }

  function handleParentMouseMove(event: ReactMouseEvent<HTMLDivElement>) {
    const target = event.target;
    if (!(target instanceof Element) || !event.currentTarget.contains(target))
      return;
    if (!target.closest(".ie-radar-sort-row")) {
      clearTimer();
      setOpenField(null);
    }
  }

  function openFlyout(
    field: Exclude<SortField, "default">,
    row: Element,
    focus = false,
  ) {
    clearTimer();
    const bounds = row.getBoundingClientRect();
    setFlyoutPosition(
      calculateFlyoutCoords(bounds, window.innerWidth, window.innerHeight),
    );
    focusFlyout.current = focus;
    setOpenField(field);
    if (focus && openField === field) {
      const selected = flyoutPanel.current?.querySelector<HTMLButtonElement>(
        '[aria-checked="true"]',
      );
      (
        selected ||
        flyoutPanel.current?.querySelector<HTMLButtonElement>(
          '[role="menuitemradio"]',
        )
      )?.focus();
    }
  }

  useEffect(() => {
    if (openField) {
      const row = sortMenu.current?.querySelector(
        `[data-sort-trigger="${openField}"]`,
      )?.parentElement;
      const panel = flyoutPanel.current;
      if (row && panel)
        setFlyoutPosition(
          calculateFlyoutCoords(
            row.getBoundingClientRect(),
            window.innerWidth,
            window.innerHeight,
            panel.offsetWidth,
            panel.offsetHeight,
          ),
        );
    }
    if (openField && focusFlyout.current) {
      const selected = flyoutPanel.current?.querySelector<HTMLButtonElement>(
        '[role="menuitemradio"][aria-checked="true"]',
      );
      (
        selected ||
        flyoutPanel.current?.querySelector<HTMLButtonElement>(
          '[role="menuitemradio"]',
        )
      )?.focus();
      focusFlyout.current = false;
    }
  }, [openField]);

  useEffect(() => {
    if (!sortOpen) return;
    sortMenu.current
      ?.querySelector<HTMLButtonElement>("[data-sort-trigger]")
      ?.focus();
    const dismissOutside = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !sortContainer.current?.contains(event.target) &&
        !flyoutPanel.current?.contains(event.target)
      )
        closeSort();
    };
    const dismissEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSort();
        sortTrigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", dismissEscape);
    window.addEventListener("resize", closeSort);
    const dismissScroll = (event: Event) => {
      if (
        !(event.target instanceof Node) ||
        (!flyoutPanel.current?.contains(event.target) &&
          !sortMenu.current?.contains(event.target))
      )
        closeSort();
    };
    window.addEventListener("scroll", dismissScroll, true);
    return () => {
      clearTimer();
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", dismissEscape);
      window.removeEventListener("resize", closeSort);
      window.removeEventListener("scroll", dismissScroll, true);
    };
  }, [sortOpen]);

  function navigateSortMenu(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Tab") {
      closeSort();
      return;
    }
    const submenu = (event.target as HTMLElement).closest(
      ".ie-radar-sort-flyout",
    );
    if (submenu && event.key === "ArrowLeft") {
      event.preventDefault();
      setOpenField(null);
      sortMenu.current
        ?.querySelector<HTMLButtonElement>(`[data-sort-trigger="${openField}"]`)
        ?.focus();
      return;
    }
    const options = Array.from(
      submenu
        ? submenu.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')
        : sortMenu.current?.querySelectorAll<HTMLButtonElement>(
            "[data-sort-trigger], [data-sort-reset]",
          ) || [],
    );
    const index = options.indexOf(document.activeElement as HTMLButtonElement);
    let next: number;
    if (event.key === "ArrowDown") next = (index + 1) % options.length;
    else if (event.key === "ArrowUp")
      next = (index - 1 + options.length) % options.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else return;
    event.preventDefault();
    options[next]?.focus();
  }

  function searchCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanTicker = query.trim().toUpperCase();
    if (cleanTicker) navigate("/company/" + encodeURIComponent(cleanTicker));
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
          <StateMessage
            kind="error"
            title="Unable to load Radar"
            actions={
              <button className="ie-button" onClick={retry}>
                Retry Radar
              </button>
            }
          >
            Failed to fetch current signals.
          </StateMessage>
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell
      navigation={shellNavigation}
      utility={
        <button className="ie-button" onClick={startTourManually}>
          🧭 Take a Tour
        </button>
      }
    >
      <ReactJoyride
        key={tourKey}
        steps={tourSteps}
        run={runTour}
        continuous={true}
        showSkipButton={true}
        tooltipComponent={MascotTooltip}
        callback={handleJoyrideCallback}
        disableScrollParentFix={true}
        styles={{
          options: { zIndex: 10000, primaryColor: "var(--ie-primary)" },
        }}
      />

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
              <div
                className="ie-radar-sort"
                ref={sortContainer}
                onMouseEnter={clearTimer}
                onMouseLeave={handleParentMouseLeave}
              >
                <button
                  className="ie-button"
                  type="button"
                  id="radar-sort-trigger"
                  ref={sortTrigger}
                  aria-haspopup="menu"
                  aria-expanded={sortOpen}
                  aria-controls={sortOpen ? "radar-sort-menu" : undefined}
                  onClick={() => {
                    setSortOpen((open) => !open);
                    setOpenField(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                      event.preventDefault();
                      setSortOpen(true);
                    }
                  }}
                >
                  Sort
                </button>
                {sortOpen && (
                  <div
                    className="ie-radar-sort-menu"
                    id="radar-sort-menu"
                    role="menu"
                    aria-labelledby="radar-sort-trigger"
                    ref={sortMenu}
                    onKeyDown={navigateSortMenu}
                    onMouseMove={handleParentMouseMove}
                  >
                    {sortOptions.map((option) => {
                      const direction =
                        sort.field === option.key ? sort.direction : "none";
                      return (
                        <div
                          className="ie-radar-sort-row"
                          key={option.key}
                          role="none"
                          onMouseEnter={(event) => {
                            if (
                              event.relatedTarget instanceof Node &&
                              flyoutPanel.current?.contains(
                                event.relatedTarget,
                              ) &&
                              openField === option.key
                            ) {
                              clearTimer();
                              return;
                            }
                            openFlyout(option.key, event.currentTarget);
                          }}
                        >
                          <button
                            type="button"
                            role="menuitem"
                            tabIndex={-1}
                            id={`sort-field-${option.key}`}
                            data-sort-trigger={option.key}
                            aria-haspopup="menu"
                            aria-expanded={openField === option.key}
                            aria-controls={
                              openField === option.key
                                ? `sort-options-${option.key}`
                                : undefined
                            }
                            data-active={openField === option.key}
                            onFocus={() => {
                              if (openField !== option.key) setOpenField(null);
                            }}
                            onClick={(event) =>
                              openFlyout(
                                option.key,
                                event.currentTarget.parentElement!,
                                true,
                              )
                            }
                            onKeyDown={(event) => {
                              if (event.key === "ArrowRight") {
                                event.preventDefault();
                                openFlyout(
                                  option.key,
                                  event.currentTarget.parentElement!,
                                  true,
                                );
                              }
                            }}
                          >
                            <span className="ie-radar-sort-label">
                              {option.label}
                            </span>
                            <span className="ie-radar-sort-badge">
                              {sortLabel(option.key, direction)}
                            </span>
                          </button>
                          {openField === option.key &&
                            createPortal(
                              <div
                                className="ie-radar-sort-flyout"
                                role="menu"
                                ref={flyoutPanel}
                                style={flyoutPosition}
                                onMouseEnter={clearTimer}
                                onMouseLeave={handleFlyoutMouseLeave}
                                id={`sort-options-${option.key}`}
                                aria-labelledby={`sort-field-${option.key}`}
                              >
                                {directionOptions(option.key).map((choice) => (
                                  <button
                                    type="button"
                                    key={choice.direction}
                                    role="menuitemradio"
                                    tabIndex={-1}
                                    aria-checked={
                                      direction === choice.direction
                                    }
                                    onClick={() => {
                                      setSort({
                                        field: option.key,
                                        direction: choice.direction,
                                      });
                                      closeSort();
                                      sortTrigger.current?.focus();
                                    }}
                                  >
                                    {choice.label}
                                  </button>
                                ))}
                              </div>,
                              document.body,
                            )}
                        </div>
                      );
                    })}
                    <button
                      className="ie-radar-sort-reset"
                      type="button"
                      role="menuitem"
                      tabIndex={-1}
                      data-sort-reset
                      onMouseEnter={() => {
                        clearTimer();
                        setOpenField(null);
                      }}
                      onFocus={() => setOpenField(null)}
                      onClick={() => {
                        setSort({ field: "default", direction: "none" });
                        closeSort();
                        sortTrigger.current?.focus();
                      }}
                    >
                      Default
                    </button>
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
        <p className="ie-description ie-radar-description">
          High score indicates research priority, not an investment
          recommendation.
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
                  <td className="ie-number">{numeric(item.anomaly_score)}</td>
                  <td className="ie-number">{numeric(item.activity_score)}</td>
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
