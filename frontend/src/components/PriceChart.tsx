import { useMemo } from 'react';
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
  const markers = useMemo(() => {
    return transactions
      .filter(t => t.is_p0_qualifying && t.filing_date)
      .map(t => {
        const pricePoint = prices.find(p => p.date === t.filing_date);
        return {
          ...t,
          chartPrice: pricePoint?.analysis_price || pricePoint?.close || 0
        };
      })
      .filter(t => t.chartPrice > 0);
  }, [prices, transactions]);

  if (!prices.length) {
    return <div className="ie-muted">No price history available.</div>;
  }

  return (
    <div style={{ width: '100%', height: 400 }}>
      <ResponsiveContainer>
        <LineChart data={prices} margin={{ top: 20, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--ie-border)" />
          <XAxis 
            dataKey="date" 
            tick={{ fontSize: 12, fill: 'var(--ie-muted)' }} 
            tickFormatter={(val) => val.substring(5)} 
            tickMargin={10}
          />
          <YAxis 
            domain={['auto', 'auto']} 
            tick={{ fontSize: 12, fill: 'var(--ie-muted)' }} 
            tickFormatter={(val) => `$${val.toFixed(0)}`}
            width={60}
          />
          <Tooltip 
            contentStyle={{ borderRadius: '8px', border: '1px solid var(--ie-border)', boxShadow: 'var(--ie-shadow)' }}
            labelStyle={{ fontWeight: 600, color: 'var(--ie-text)', marginBottom: '4px' }}
          />
          <Line 
            type="monotone" 
            dataKey="analysis_price" 
            stroke="var(--ie-text)" 
            strokeWidth={2} 
            dot={false}
            animationDuration={300}
          />
          
          {markers.map((marker, idx) => (
            <ReferenceDot
              key={`${marker.transaction_id}-${idx}`}
              x={marker.filing_date}
              y={marker.chartPrice}
              r={5}
              fill="var(--ie-primary)"
              stroke="#fff"
              strokeWidth={2}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}