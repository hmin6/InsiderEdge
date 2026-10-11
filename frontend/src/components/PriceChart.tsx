import { formatCurrency } from "../utils/format";
import { createPortal } from "react-dom";
import { useMemo, useEffect, useState, useRef, useId, type Dispatch, type SetStateAction } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceDot,
  usePlotArea,
  useXAxisScale,
  useYAxisScale,
} from "recharts";
import { PricePoint, InsiderTransaction } from "../types/api";

interface PriceChartProps {
  prices: PricePoint[];
  transactions: InsiderTransaction[];
}

function InspectionLayer({ prices, allPrices, readoutHost, onZoom, markedPoints, setMarkedPoints }: {
  prices: PricePoint[]; allPrices: PricePoint[]; readoutHost: HTMLDivElement | null;
  onZoom: (fraction: number, delta: number) => void;
  markedPoints: PricePoint[];
  setMarkedPoints: Dispatch<SetStateAction<PricePoint[]>>;
}) {
  const interactionArea = useRef<SVGRectElement>(null);
  const plot = usePlotArea();
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  const pointerStart = useRef<number | null>(null);
  const moved = useRef(false);
  const [pinned, setPinned] = useState<PricePoint | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragging = useRef(false);
  useEffect(() => { setMarkedPoints([]); setPinned(null); dragging.current = false; setIsDragging(false); }, [allPrices]);
  useEffect(() => {
    const area = interactionArea.current;
    if (!area) return;
    const wheel = (event: WheelEvent) => {
      if (dragging.current || event.deltaY === 0) return;
      event.preventDefault();
      const bounds = area.getBoundingClientRect();
      onZoom(Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)), event.deltaY);
      setPinned(null);
    };
    area.addEventListener("wheel", wheel, { passive: false });
    return () => area.removeEventListener("wheel", wheel);
  }, [onZoom, plot]);
  if (!plot || !xScale || !yScale) return null;
  const points = prices.filter(point => point.analysis_price !== null && Number.isFinite(point.analysis_price) && point.analysis_price > 0);
  const inspect = (event: React.PointerEvent<SVGRectElement>) => {
    const svg = event.currentTarget.ownerSVGElement;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix || !points.length) return;
    const cursor = svg.createSVGPoint();
    cursor.x = event.clientX; cursor.y = event.clientY;
    const x = cursor.matrixTransform(matrix.inverse()).x;
    const nearbyMark = markedPoints.filter(mark => points.some(point => point.date === mark.date))
      .reduce<PricePoint | null>((best, mark) => {
        const distance = Math.abs(Number(xScale(mark.date)) - x);
        return distance <= 12 && (!best || distance < Math.abs(Number(xScale(best.date)) - x)) ? mark : best;
      }, null);
    const nearest = nearbyMark ?? points.reduce((best, point) =>
      Math.abs(Number(xScale(point.date)) - x) < Math.abs(Number(xScale(best.date)) - x) ? point : best);
    setPinned(nearest);
    return nearest;
  };
  const toggleMark = (point: PricePoint) => {
    setMarkedPoints(current => current.some(mark => mark.date === point.date)
      ? current.filter(mark => mark.date !== point.date) : [...current, point]);
  };
  const displayed = allPrices.filter(point => point.analysis_price !== null && Number.isFinite(point.analysis_price) && point.analysis_price > 0).reduce<PricePoint | null>((latest, point) =>
    !latest || point.date > latest.date ? point : latest, null);
  return <g>
    {displayed && readoutHost && createPortal(<div className="ie-price-chart-readout">
      <strong>{formatCurrency(displayed.analysis_price)}</strong>
      <span>{displayed.date}</span>
    </div>, readoutHost)}

    <rect ref={interactionArea} x={plot.x} y={plot.y} width={plot.width} height={plot.height} fill="transparent"
      style={{ cursor: 'crosshair', touchAction: 'none' }} tabIndex={0} role="slider"
      aria-label="Price inspection; use arrow keys to inspect dates and Enter to toggle a guideline"
      aria-valuemin={0} aria-valuemax={Math.max(0, points.length - 1)}
      aria-valuenow={Math.max(0, points.findIndex(point => point.date === pinned?.date))}
      aria-valuetext={pinned ? `${pinned.date}: ${formatCurrency(pinned.analysis_price)}` : 'No pinned price'}
      onKeyDown={event => {
        if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'z') {
          event.preventDefault(); setMarkedPoints(current => current.slice(0, -1));
          setSelectedDate(null); setPinned(null); return;
        }
        if (["+", "=", "-"].includes(event.key)) {
          event.preventDefault(); onZoom(0.5, event.key === "-" ? 1 : -1); return;
        }
        if (event.key === 'Escape') { setPinned(null); return; }
        if ((event.key === 'Enter' || event.key === ' ') && pinned) {
          event.preventDefault(); toggleMark(pinned); return;
        }
        if (!points.length || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const index = points.findIndex(point => point.date === pinned?.date);
        setPinned(points[Math.max(0, Math.min(points.length - 1, index < 0 ? 0 : index + (event.key === 'ArrowRight' ? 1 : -1)))]);
      }}
      onPointerDown={event => {
        if (event.button !== 0) return;
        event.currentTarget.focus({ preventScroll: true });
        pointerStart.current = event.clientX; moved.current = false;
        dragging.current = true; setIsDragging(true); inspect(event);
        event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={event => {
        if (dragging.current && pointerStart.current !== null && Math.abs(event.clientX - pointerStart.current) > 4) moved.current = true;
        inspect(event);
      }}
      onPointerLeave={() => { if (!dragging.current) setPinned(null); }}
      onBlur={() => { if (!dragging.current) setPinned(null); }}
      onPointerUp={event => {
        if (!dragging.current) return;
        const point = inspect(event);
        if (point && !moved.current) toggleMark(point);
        setPinned(null); dragging.current = false; setIsDragging(false);
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      }} onPointerCancel={() => { dragging.current = false; setIsDragging(false); }}
      onLostPointerCapture={() => { dragging.current = false; setIsDragging(false); }} />
    {[...markedPoints.filter(mark => !isDragging || mark.date !== pinned?.date), ...(pinned ? [pinned] : [])]
      .filter((point, index, all) => all.findIndex(other => other.date === point.date) === index)
      .filter(point => points.some(visible => visible.date === point.date))
      .sort((a, b) => Number(a.date === selectedDate) - Number(b.date === selectedDate))
      .map(point => {
        const x = Number(xScale(point.date));
        if (!Number.isFinite(x)) return null;
        const active = point.date === pinned?.date;
        const selected = point.date === selectedDate;
        const y = Number(yScale(point.analysis_price));
        const saved = markedPoints.some(mark => mark.date === point.date);
        const labelX = Math.max(plot.x + Math.min(45, plot.width / 2), Math.min(x, plot.x + plot.width - Math.min(45, plot.width / 2)));
        return <g key={point.date} pointerEvents="none">
          {(saved || active) && <text x={labelX} y={plot.y - 25} textAnchor="middle"
            fill={selected ? '#f97316' : 'var(--ie-text)'} fontSize={16}
            fontWeight={selected ? 700 : 400}
            stroke={selected ? 'var(--ie-panel)' : undefined} strokeWidth={selected ? 4 : undefined}
            paintOrder="stroke" pointerEvents={saved ? 'auto' : 'none'}
            style={{ cursor: saved ? 'pointer' : undefined }}
            role={saved ? 'button' : undefined} tabIndex={saved ? 0 : undefined}
            aria-label={saved ? `Highlight guideline for ${point.date}, ${formatCurrency(point.analysis_price)}` : undefined}
            aria-pressed={saved ? selected : undefined}
            onClick={event => { event.stopPropagation(); setSelectedDate(current => current === point.date ? null : point.date); }}
            onKeyDown={event => {
              if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'z') {
                event.preventDefault(); event.stopPropagation();
                setMarkedPoints(current => current.slice(0, -1));
                setSelectedDate(null); setPinned(null);
                interactionArea.current?.focus({ preventScroll: true }); return;
              }
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault(); event.stopPropagation(); setSelectedDate(current => current === point.date ? null : point.date);
              }
            }}>
            <tspan x={labelX}>{formatCurrency(point.analysis_price)}</tspan>
            <tspan x={labelX} dy={13} fill={selected ? '#f97316' : 'var(--ie-muted)'}>{point.date}</tspan>
          </text>}
          <line x1={x} x2={x} y1={plot.y} y2={plot.y + plot.height}
            stroke={selected ? '#f97316' : active ? 'var(--ie-text)' : 'var(--ie-primary)'}
            strokeWidth={selected ? 3.5 : active ? 2.5 : 2} strokeOpacity={selected || active ? 1 : 0.9}
            strokeDasharray={active ? undefined : '5 3'} />
          {active && Number.isFinite(y) && <circle cx={x} cy={y} r={4}
            fill="var(--ie-text)" stroke="var(--ie-workspace)" strokeWidth={2} />}

        </g>;
      })}

  </g>;
}

export function PriceChart({ prices, transactions }: PriceChartProps) {
  const [markedPoints, setMarkedPoints] = useState<PricePoint[]>([]);
  const gradientId = `price-direction-${useId().replace(/:/g, '')}`;
  const [zoomRange, setZoomRange] = useState<{ start: number; end: number } | null>(null);
  useEffect(() => { setZoomRange(null); }, [prices]);
  const start = zoomRange?.start ?? 0;
  const end = zoomRange?.end ?? prices.length;
  const visiblePrices = prices.slice(start, end);
  const zoom = (fraction: number, delta: number) => {
    setZoomRange(current => {
      const from = current?.start ?? 0;
      const to = current?.end ?? prices.length;
      const count = to - from;
      const nextCount = Math.min(prices.length, Math.max(Math.min(5, prices.length),
        delta < 0 ? Math.floor(count * 0.8) : Math.ceil(count * 1.25)));
      const anchor = from + fraction * Math.max(0, count - 1);
      const nextStart = Math.max(0, Math.min(prices.length - nextCount,
        Math.round(anchor - fraction * Math.max(0, nextCount - 1))));
      return nextCount === prices.length ? null : { start: nextStart, end: nextStart + nextCount };
    });
  };
  const [readoutHost, setReadoutHost] = useState<HTMLDivElement | null>(null);
  const [reducedMotion, setReducedMotion] = useState(true);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  const markers = useMemo(() => {
    return transactions
      .filter((t) => t.is_p0_qualifying && t.filing_date)
      .map((t) => {
        const pricePoint = prices.find((p) => p.date === t.filing_date);
        return {
          ...t,
          chartPrice: pricePoint?.analysis_price ?? null,
        };
      })
      .filter(
        (t): t is typeof t & { chartPrice: number } =>
          t.chartPrice !== null &&
          Number.isFinite(t.chartPrice) &&
          t.chartPrice > 0,
      );
  }, [prices, transactions]);

  if (!prices.length) {
    return <div className="ie-muted">No price history available.</div>;
  }

  return (
    <div ref={setReadoutHost} className="ie-price-chart" style={{ width: "100%", height: 400, position: "relative" }}>
      <div style={{ position: "absolute", top: 0, right: 0, zIndex: 2, display: "flex", gap: 4 }}>
        <button type="button" className="ie-button" disabled={!markedPoints.length}
          onClick={() => setMarkedPoints([])}>Clear marks</button>
        {zoomRange && <button type="button" className="ie-button"
          onClick={() => setZoomRange(null)}>Reset zoom</button>}
      </div>
      <ResponsiveContainer>
        <LineChart
          accessibilityLayer={false}
          data={visiblePrices}
          margin={{ top: 100, right: 20, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#15803d" />
              <stop offset="25%" stopColor="#4ade80" />
              <stop offset="50%" stopColor="#facc15" />
              <stop offset="75%" stopColor="#f87171" />
              <stop offset="100%" stopColor="#b91c1c" />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            strokeOpacity={0.35}
            vertical={false}
            stroke="var(--ie-border)"
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 14, fill: "var(--ie-muted)" }}
            tickFormatter={(val) => val.substring(5)}
            tickMargin={10}
            minTickGap={32}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 14, fill: "var(--ie-muted)" }}
            tickFormatter={formatCurrency}
            width={100}
          />
          <Line
            type="monotone"
            dataKey="analysis_price"
            stroke={`url(#${gradientId})`}
            strokeWidth={2}
            dot={false}
            activeDot={{
              r: 6,
              fill: "var(--ie-primary)",
              stroke: "#fff",
              strokeWidth: 2,
            }}
            animationDuration={300}
            isAnimationActive={!reducedMotion}
          />

          {markers.filter(marker => visiblePrices.some(point => point.date === marker.filing_date)).map((marker, idx) => (
            <ReferenceDot
              key={`${marker.transaction_id}-${idx}`}
              x={marker.filing_date}
              y={marker.chartPrice}
              r={6}
              fill="var(--ie-primary)"
              stroke="#fff"
              strokeWidth={2.5}
            />
          ))}
          <InspectionLayer prices={visiblePrices} allPrices={prices} readoutHost={readoutHost} onZoom={zoom}
            markedPoints={markedPoints} setMarkedPoints={setMarkedPoints} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
