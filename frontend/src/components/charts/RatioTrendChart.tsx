"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const COLORS = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed"];

export default function RatioTrendChart({
  data,
  seriesKeys,
}: {
  data: { fiscal_year: number; [key: string]: number | null }[];
  seriesKeys: string[];
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-black/10 dark:stroke-white/10" />
        <XAxis dataKey="fiscal_year" tickFormatter={(v) => `FY${v}`} fontSize={12} />
        <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={12} width={48} />
        <Tooltip
          formatter={(value) => `${(Number(value) * 100).toFixed(1)}%`}
          labelFormatter={(v) => `FY${v}`}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {seriesKeys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
