"use client";

import { fmtCurrency, fmtPercent } from "@/lib/format";

export default function SensitivityHeatmap({
  waccValues,
  growthValues,
  prices,
  centerPrice,
}: {
  waccValues: number[];
  growthValues: number[];
  prices: (number | null)[][];
  centerPrice?: number;
}) {
  const flat = prices.flat().filter((v): v is number => v !== null);
  const min = Math.min(...flat);
  const max = Math.max(...flat);

  function colorFor(v: number | null) {
    if (v === null) return "transparent";
    const t = max === min ? 0.5 : (v - min) / (max - min);
    // red (low) -> yellow -> green (high)
    const hue = 0 + t * 120;
    return `hsl(${hue}, 65%, 45%)`;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="border border-black/10 bg-black/[0.02] p-2 dark:border-white/10 dark:bg-white/[0.03]">
              WACC \ g
            </th>
            {growthValues.map((g) => (
              <th key={g} className="border border-black/10 p-2 font-medium dark:border-white/10">
                {fmtPercent(g)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {waccValues.map((w, ri) => (
            <tr key={w}>
              <th className="border border-black/10 bg-black/[0.02] p-2 font-medium dark:border-white/10 dark:bg-white/[0.03]">
                {fmtPercent(w)}
              </th>
              {prices[ri].map((price, ci) => (
                <td
                  key={ci}
                  className="border border-black/10 p-2 text-center tabular-nums text-white dark:border-white/10"
                  style={{ backgroundColor: colorFor(price) }}
                >
                  {price === null ? "—" : fmtCurrency(price)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {centerPrice !== undefined ? (
        <p className="mt-2 text-xs text-black/50 dark:text-white/50">
          Current assumptions imply {fmtCurrency(centerPrice)}.
        </p>
      ) : null}
    </div>
  );
}
