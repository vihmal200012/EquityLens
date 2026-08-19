"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const TABS = [
  { href: "", label: "Overview" },
  { href: "/financials", label: "Financials" },
  { href: "/ratios", label: "Ratios" },
  { href: "/dcf", label: "DCF" },
  { href: "/comparables", label: "Comparables" },
  { href: "/ai", label: "AI Assistant" },
  { href: "/report", label: "Report" },
];

export default function CompanyTabs({ ticker }: { ticker: string }) {
  const pathname = usePathname();
  const base = `/company/${ticker}`;

  return (
    <nav className="flex flex-wrap gap-1 border-b border-black/10 dark:border-white/10">
      {TABS.map((tab) => {
        const href = `${base}${tab.href}`;
        const active = pathname === href;
        return (
          <Link
            key={tab.href}
            href={href}
            className={clsx(
              "-mb-px rounded-t-md border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "border-black text-black dark:border-white dark:text-white"
                : "border-transparent text-black/50 hover:text-black dark:text-white/50 dark:hover:text-white"
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
