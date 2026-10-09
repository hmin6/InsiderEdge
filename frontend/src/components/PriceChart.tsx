import { useMemo, useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot
} from 'recharts';
import { PricePoint, InsiderTransaction } from '../types/api';

interface PriceChartProps {
  prices: PricePoint[];
  transactions: InsiderTransaction[];
}

export function PriceChart({ prices, transactions }: PriceChartProps) {
  const [reducedMotion, setReducedMotion] = useState(true);
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  const markers = useMemo(() => {
    return transactions
      .filter(t => t.is_p0_qualifying && t.filing_date)
      .map(t => {
        const pricePoint = prices.find(p => p.date === t.filing_date);
        return {
          ...t,
          chartPrice: pricePoint?.analysis_price ?? null
        };
      })
      .filter((t): t is typeof t & { chartPrice: number } => t.chartPrice !== null && Number.isFinite(t.chartPrice) && t.chartPrice > 0);
  }, [prices, transactions]);

  if (!prices.length) {
    return <div className="ie-muted">No price history available.</div>;
  }

  return (
    <div className="ie-price-chart" style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <LineChart data={prices} margin={{ top: 20, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--ie-border)" />
          <XAxis 
            dataKey="date" 
            tick={{ fontSize: 14, fill: 'var(--ie-muted)' }}
            tickFormatter={(val) => val.substring(5)} 
            tickMargin={10}
            minTickGap={32}
          />
          <YAxis 
            domain={['auto', 'auto']} 
            tick={{ fontSize: 14, fill: 'var(--ie-muted)' }}
            tickFormatter={(val) => `$${val.toFixed(0)}`}
            width={72}
          />
          <Tooltip 
            contentStyle={{ borderRadius: '8px', border: '1px solid var(--ie-border)', boxShadow: 'var(--ie-shadow)' }}
            labelStyle={{ fontWeight: 600, color: 'var(--ie-text)', marginBottom: '4px' }}
            formatter={(value) => typeof value === 'number' ? `$${value.toFixed(2)}` : String(value)}
          />
          <Line 
            type="monotone" 
            dataKey="analysis_price" 
            name="Adjustment-aware price"
            stroke="var(--ie-text)" 
            strokeWidth={2.5}
            dot={false}
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
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
