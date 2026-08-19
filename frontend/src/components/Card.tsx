import { ReactNode } from "react";
import clsx from "clsx";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/[0.03]",
        className
      )}
    >
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <Card>
      <div className="text-xs font-medium uppercase tracking-wide text-black/50 dark:text-white/50">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub ? <div className="mt-1 text-sm text-black/50 dark:text-white/50">{sub}</div> : null}
    </Card>
  );
}
