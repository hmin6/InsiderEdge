import { RadarComponentValues } from "../components/RadarComponentValues";
import { selectResearchPriority } from "../components/ResearchPriorityValue";
import { ResearchPriorityValue } from "../components/ResearchPriorityValue";
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
import { Joyride, TooltipRenderProps } from "react-joyride";
const JoyrideComponent = Joyride as any;
import { fetchRadar, usingResearchMocks } from "../api/client";
import { useResource } from "../hooks/useResource";
import { rankRadar } from "../components/ResearchStates";
import type { RadarItem } from "../types/api";
import {
  AppShell,
  PageContainer,
  ProductHeader,
  PanelSkeleton,
  StateMessage,
} from "../components";

const EdgeMascot = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 120 120"
    style={{ width: "85px", height: "85px", flexShrink: 0 }}
  >
    <circle cx="60" cy="60" r="60" fill="#090e17" />
    <circle
      cx="60"
      cy="60"
      r="48"
      fill="none"
      stroke="#2a374f"
      strokeWidth="2"
      strokeDasharray="4 4"
    />
    <path
      d="M60 12 A 48 48 0 0 1 108 60"
      fill="none"
      stroke="#3b82f6"
      strokeWidth="4"
      strokeLinecap="round"
    />
    <circle cx="60" cy="60" r="26" fill="#1e3a8a" />
    <circle cx="60" cy="60" r="12" fill="#60a5fa" />
    <path
      d="M60 40 Q60 60 40 60 Q60 60 60 80 Q60 60 80 60 Q60 60 60 40 Z"
      fill="#ffffff"
      opacity="0.9"
    />
  </svg>
);

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
      padding: "24px",
      borderRadius: "16px",
      color: "var(--ie-text)",
      maxWidth: "550px",
      gap: "20px",
      boxShadow: "0 10px 40px rgba(0,0,0,0.6)",
      border: "1px solid var(--ie-border)",
      backdropFilter: "blur(12px)",
      zIndex: 10000,
    }}
  >
    <EdgeMascot />
    <div style={{ flexGrow: 1 }}>
      <div
        style={{ fontSize: "17px", marginBottom: "20px", lineHeight: "1.6" }} // <-- Increased text size and line height
      >
        {step.content}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
        <button
          type="button"
          {...skipProps}
          className="ie-button"
          style={{
            background: "transparent",
            border: "none",
            color: "var(--ie-muted)",
            fontSize: "15px",
          }}
        >
          Skip
        </button>
        {index > 0 && (
          <button
            type="button"
            {...backProps}
            className="ie-button"
            style={{
              background: "transparent",
              border: "none",
              fontSize: "15px",
            }}
          >
            Back
          </button>
        )}
        <button
          type="button"
          {...primaryProps}
          className="ie-button ie-button--primary"
          style={{ fontSize: "15px" }}
        >
          {isLastStep ? "Got it!" : "Next"}
        </button>
      </div>
    </div>
  </div>
);
const tourSteps: any[] = [
  {
    target: "body",
    placement: "center",
    content:
      "Welcome to InsiderEdge! This platform identifies institutional-grade quantitative equity research by detecting anomalous insider trading clusters.",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-table",
    placement: "top",
    content:
      "Here is our Market Radar queue. It constantly scans recent SEC Form 4 filings and ranks them based on Mahalanobis distance, clustered buying, and XGBoost machine learning predictions.",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-sort",
    placement: "bottom",
    content:
      "You can sort the generated signals by different quantitative components. Try sorting by 'Anomaly' or 'Market Dislocation'!",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-quick-search",
    placement: "bottom",
    content:
      "If you want to evaluate a specific stock, type its ticker here. We normalize the SEC data and calculate the event study on the fly.",
    disableBeacon: true,
  },
  {
    target: ".ie-radar-table tbody tr:first-child",
    placement: "bottom",
    content:
      "Click on any company row here to dive into the deep quantitative metrics, our ML evaluation, and the Gemini AI explanation for this exact event!",
    disableBeacon: true,
  },
];

type SortField =
  | "default"
  | "company"
  | "status"
  | "anomaly"
  | "statistical"
  | "activity"
  | "dislocation"
  | "model_prob"
  | "priority";
type PriorityClass = "Complete" | "Estimated Activity" | "Provisional";
const priorityClasses: PriorityClass[] = [
  "Complete",
  "Estimated Activity",
  "Provisional",
];
type SortDirection = "none" | "asc" | "desc";
const sortOptions: { key: Exclude<SortField, "default">; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "company", label: "Company" },
  { key: "anomaly", label: "Anomaly" },
  { key: "activity", label: "Activity" },
  { key: "statistical", label: "Statistical Evidence" },
  { key: "dislocation", label: "Dislocation" },
  { key: "model_prob", label: "Model Probability" },
  { key: "priority", label: "Research Priority Score" },
];

function calculateFlyoutCoords(
  rect: { right: number; top: number; left?: number },
  viewportWidth: number,
  viewportHeight: number,
  panelWidth = 220,
  panelHeight = 110,
  rightGap = -10,
  preferLeft = false,
) {
  const edge = 12;
  const width = Math.min(panelWidth, Math.max(0, viewportWidth - edge * 2));
  const height = Math.min(panelHeight, Math.max(0, viewportHeight - edge * 2));
  return {
    left: Math.max(
      edge,
      Math.min(
        preferLeft
          ? (rect.left ?? rect.right) - width - 4
          : rect.right + rightGap,
        viewportWidth - width - edge,
      ),
    ),
    top: Math.max(edge, Math.min(rect.top, viewportHeight - height - edge)),
  };
}

function sortLabel(field: SortField, direction: SortDirection) {
  if (direction === "none") return "—";
  if (field === "company") return direction === "asc" ? "A-Z" : "Z-A";
  if (field === "status") return "Sections";
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
      : [
          { direction: "desc" as const, label: "High → Low (Descending)" },
          { direction: "asc" as const, label: "Low → High (Ascending)" },
        ]),
  ];
}

const metricFields = {
  anomaly: "anomaly_score",
  activity: "activity_score",
  statistical: "statistical_score",
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
  if (key === "priority") {
    const left = selectResearchPriority(
      a.insider_edge_score,
      a.score_status,
      a.quantitative_coverage,
    );
    const right = selectResearchPriority(
      b.insider_edge_score,
      b.score_status,
      b.quantitative_coverage,
    );
    const classes = ["Complete", "Provisional", "Estimated Activity"];
    const bucket = (label?: string) =>
      label ? classes.indexOf(label) : classes.length;
    const partition = bucket(left?.label) - bucket(right?.label);
    if (partition) return partition;
    return left && right ? multiplier * (left.value - right.value) : 0;
  }
  if (key === "company")
    return (
      multiplier *
      a.ticker.localeCompare(b.ticker, "en", { sensitivity: "base" })
    );
  if (key === "status") return 0;
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
  const [statusSections, setStatusSections] = useState(false);
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
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

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
  const tableRows: { item?: RadarItem; section?: string }[] = statusSections
    ? [
        ...priorityClasses.filter(
          (category) => category !== "Estimated Activity",
        ),
        "Estimated Activity",
        "Unavailable",
      ].flatMap((category) => {
        const rows = filteredData.filter(
          (item) =>
            (selectResearchPriority(
              item.insider_edge_score,
              item.score_status,
              item.quantitative_coverage,
            )?.label ?? "Unavailable") === category,
        );
        return category === "Unavailable" && !rows.length
          ? []
          : [{ section: category }, ...rows.map((item) => ({ item }))];
      })
    : filteredData.map((item) => ({ item }));

  useEffect(() => {
    if (data.length > 0) {
      const hasSeenRadarTour = localStorage.getItem(
        "ie_has_seen_radar_tour_v4",
      );
      if (!hasSeenRadarTour) {
        const timer = setTimeout(() => {
          localStorage.setItem("ie_has_seen_radar_tour_v4", "true");
          setRunTour(true);
        }, 800);
        return () => clearTimeout(timer);
      }
    }
  }, [data.length]);

  const handleJoyrideCallback = (joyrideData: any) => {
    const { status } = joyrideData;
    if (["finished", "skipped"].includes(status)) {
      setRunTour(false);
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
    if (related instanceof Node && flyoutPanel.current?.contains(related)) {
      clearTimer();
      return;
    }
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
      if (openField === "priority") {
        scheduleClose();
        return;
      }
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
      calculateFlyoutCoords(
        bounds,
        window.innerWidth,
        window.innerHeight,
        220,
        160,
        -10,
        false,
      ),
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
          '[role="menuitemradio"], [role="menuitem"]',
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
            -10,
            false,
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
          '[role="menuitemradio"], [role="menuitem"]',
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
        ? submenu.querySelectorAll<HTMLButtonElement>(
            '[role="menuitemradio"], [role="menuitem"]',
          )
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
      {isMounted && (
        <JoyrideComponent
          key={tourKey}
          steps={tourSteps}
          run={runTour}
          continuous={true}
          disableBeacon={true}
          showSkipButton={true}
          tooltipComponent={MascotTooltip}
          callback={handleJoyrideCallback}
          styles={{
            options: { zIndex: 10000, primaryColor: "var(--ie-primary)" },
          }}
        />
      )}

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
                          className={`ie-radar-sort-row${option.key === "company" ? " ie-radar-sort-after-status" : ""}`}
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
                            if (option.key === "status") {
                              clearTimer();
                              setOpenField(null);
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
                            aria-haspopup={
                              option.key === "status" ? undefined : "menu"
                            }
                            aria-expanded={openField === option.key}
                            aria-controls={
                              openField === option.key
                                ? `sort-options-${option.key}`
                                : undefined
                            }
                            data-active={
                              openField === option.key ||
                              (option.key === "status" && statusSections)
                            }
                            onFocus={() => {
                              if (openField !== option.key) setOpenField(null);
                            }}
                            onClick={(event) => {
                              if (option.key === "status") {
                                setStatusSections(!statusSections);
                                setSort({
                                  field: statusSections ? "default" : "status",
                                  direction: "none",
                                });
                                closeSort();
                                sortTrigger.current?.focus();
                                return;
                              }
                              openFlyout(
                                option.key,
                                event.currentTarget.parentElement!,
                                true,
                              );
                            }}
                            onKeyDown={(event) => {
                              if (
                                event.key === "ArrowRight" &&
                                option.key !== "status"
                              ) {
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
                              {option.key === "status" && statusSections
                                ? String.fromCharCode(10003)
                                : sortLabel(option.key, direction)}
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
                        setStatusSections(false);
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
          recommendation. Complete, Provisional, and Estimated Activity values
          are not directly comparable; sorting uses canonical scores only.
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
                <th>Status</th>
                <th className="ie-number">Anomaly</th>
                <th className="ie-number">Activity</th>
                <th className="ie-number">Statistical Evidence</th>
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
              {tableRows.map(({ item, section }) =>
                section ? (
                  <tr
                    key={`section-${section}`}
                    className="ie-radar-section-row"
                  >
                    <th
                      colSpan={8}
                      scope="rowgroup"
                      style={
                        section === "Unavailable"
                          ? undefined
                          : { textAlign: "center" }
                      }
                    >
                      {section}
                    </th>
                  </tr>
                ) : (
                  item && (
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
                      <td>
                        <SignalAvailability evidence={item} compact />
                      </td>
                      <RadarComponentValues item={item} />
                      <td className="ie-number ie-priority-column">
                        <ResearchPriorityValue
                          score={item.insider_edge_score}
                          status={item.score_status}
                          coverage={item.quantitative_coverage}
                        />
                      </td>
                    </tr>
                  )
                ),
              )}
            </tbody>
          </table>
        </div>
      </PageContainer>
    </AppShell>
  );
}
