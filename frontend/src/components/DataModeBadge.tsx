import clsx from "clsx";

export default function DataModeBadge({ mode }: { mode?: string }) {
  if (!mode) return null;
  const isDemo = mode === "demo";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        isDemo
          ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300"
          : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      )}
      title={
        isDemo
          ? "Synthetic demo data — not the company's real reported financials."
          : "Live data from the configured financial data provider."
      }
    >
      <span className={clsx("h-1.5 w-1.5 rounded-full", isDemo ? "bg-amber-500" : "bg-emerald-500")} />
      {isDemo ? "Demo data" : "Live data"}
    </span>
  );
}
