import { formatCurrency } from "../utils/format";
import { createPortal } from "react-dom";
import { useMemo, useEffect, useState, useRef } from "react";
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

function InspectionLayer({ prices, readoutHost }: { prices: PricePoint[]; readoutHost: HTMLDivElement | null }) {
  const plot = usePlotArea();
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  const [markedPoints, setMarkedPoints] = useState<PricePoint[]>([]);
  const pointerStart = useRef<number | null>(null);
  const moved = useRef(false);
  const [pinned, setPinned] = useState<PricePoint | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragging = useRef(false);
  useEffect(() => { setMarkedPoints([]); setPinned(null); dragging.current = false; setIsDragging(false); }, [prices]);
  if (!plot || !xScale || !yScale) return null;
  const points = prices.filter(point => point.analysis_price !== null && Number.isFinite(point.analysis_price) && point.analysis_price > 0);
  const inspect = (event: React.PointerEvent<SVGRectElement>) => {
    const svg = event.currentTarget.ownerSVGElement;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix || !points.length) return;
    const cursor = svg.createSVGPoint();
    cursor.x = event.clientX; cursor.y = event.clientY;
    const x = cursor.matrixTransform(matrix.inverse()).x;
    const nearest = points.reduce((best, point) =>
      Math.abs(Number(xScale(point.date)) - x) < Math.abs(Number(xScale(best.date)) - x) ? point : best);
    setPinned(nearest);
    return nearest;
  };
  const toggleMark = (point: PricePoint) => {
    setMarkedPoints(current => current.some(mark => mark.date === point.date)
      ? current.filter(mark => mark.date !== point.date) : [...current, point]);
  };
  const displayed = points.reduce<PricePoint | null>((latest, point) =>
    !latest || point.date > latest.date ? point : latest, null);
  return <g>
    {displayed && readoutHost && createPortal(<div className="ie-price-chart-readout">
      <strong>{formatCurrency(displayed.analysis_price)}</strong>
      <span>{displayed.date}</span>
    </div>, readoutHost)}

    <rect x={plot.x} y={plot.y} width={plot.width} height={plot.height} fill="transparent"
      style={{ cursor: 'crosshair', touchAction: 'none' }} tabIndex={0} role="slider"
      aria-label="Price inspection; use arrow keys to inspect dates and Enter to toggle a guideline"
      aria-valuemin={0} aria-valuemax={Math.max(0, points.length - 1)}
      aria-valuenow={Math.max(0, points.findIndex(point => point.date === pinned?.date))}
      aria-valuetext={pinned ? `${pinned.date}: ${formatCurrency(pinned.analysis_price)}` : 'No pinned price'}
      onKeyDown={event => {
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
        if (point) {
          if (moved.current) setMarkedPoints(current => current.some(mark => mark.date === point.date) ? current : [...current, point]);
          else toggleMark(point);
        }
        setPinned(null); dragging.current = false; setIsDragging(false);
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      }} onPointerCancel={() => { dragging.current = false; setIsDragging(false); }}
      onLostPointerCapture={() => { dragging.current = false; setIsDragging(false); }} />
    {[...markedPoints.filter(mark => !isDragging || mark.date !== pinned?.date), ...(pinned ? [pinned] : [])]
      .filter((point, index, all) => all.findIndex(other => other.date === point.date) === index)
      .map(point => {
        const x = Number(xScale(point.date));
        if (!Number.isFinite(x)) return null;
        const active = point.date === pinned?.date;
        const y = Number(yScale(point.analysis_price));
        const saved = markedPoints.some(mark => mark.date === point.date);
        const labelX = Math.max(plot.x + Math.min(45, plot.width / 2), Math.min(x, plot.x + plot.width - Math.min(45, plot.width / 2)));
        return <g key={point.date} pointerEvents="none">
          {(saved || active) && <text x={labelX} y={plot.y - 25} textAnchor="middle"
            fill="var(--ie-text)" fontSize={16}>
            <tspan x={labelX}>{formatCurrency(point.analysis_price)}</tspan>
            <tspan x={labelX} dy={13} fill="var(--ie-muted)">{point.date}</tspan>
          </text>}
          <line x1={x} x2={x} y1={plot.y} y2={plot.y + plot.height}
            stroke={active ? 'var(--ie-text)' : 'var(--ie-primary)'}
            strokeWidth={active ? 2.5 : 2} strokeOpacity={active ? 1 : 0.9}
            strokeDasharray={active ? undefined : '5 3'} />
          {active && Number.isFinite(y) && <circle cx={x} cy={y} r={4}
            fill="var(--ie-text)" stroke="var(--ie-workspace)" strokeWidth={2} />}

        </g>;
      })}

  </g>;
}

export function PriceChart({ prices, transactions }: PriceChartProps) {
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
      <ResponsiveContainer>
        <LineChart
          accessibilityLayer={false}
          data={prices}
          margin={{ top: 100, right: 20, left: 0, bottom: 0 }}
        >
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
            stroke="var(--ie-text)"
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

          {markers.map((marker, idx) => (
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
          <InspectionLayer prices={prices} readoutHost={readoutHost} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
