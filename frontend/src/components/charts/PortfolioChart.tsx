"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function PortfolioChart({
  series,
  color = "#2563eb",
  formatAsPercent = false,
}: {
  series: number[];
  color?: string;
  formatAsPercent?: boolean;
}) {
  const data = series.map((v, i) => ({ period: i, value: v }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`grad-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.35} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" className="stroke-black/10 dark:stroke-white/10" />
        <XAxis dataKey="period" fontSize={12} />
        <YAxis
          fontSize={12}
          width={56}
          tickFormatter={(v) => (formatAsPercent ? `${(v * 100).toFixed(0)}%` : v.toFixed(2))}
        />
        <Tooltip
          formatter={(v) => (formatAsPercent ? `${(Number(v) * 100).toFixed(2)}%` : Number(v).toFixed(4))}
        />
        <Area type="monotone" dataKey="value" stroke={color} fill={`url(#grad-${color.replace("#", "")})`} strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
