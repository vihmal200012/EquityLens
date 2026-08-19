"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Nav() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [health, setHealth] = useState<"checking" | "up" | "down">("checking");

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(() => !cancelled && setHealth("up"))
      .catch(() => !cancelled && setHealth("down"));
    return () => {
      cancelled = true;
    };
  }, []);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    const ticker = query.trim().toUpperCase();
    if (ticker) {
      router.push(`/company/${ticker}`);
      setQuery("");
    }
  }

  return (
    <header className="sticky top-0 z-10 border-b border-black/10 bg-white/80 backdrop-blur dark:border-white/10 dark:bg-black/70">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          EquityLens
        </Link>

        <form onSubmit={onSearch} className="flex-1 max-w-sm">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ticker (e.g. AAPL)"
            className="w-full rounded-md border border-black/15 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
          />
        </form>

        <nav className="flex items-center gap-4 text-sm">
          <Link href="/" className="text-black/70 hover:text-black dark:text-white/70 dark:hover:text-white">
            Dashboard
          </Link>
          <Link
            href="/portfolio"
            className="text-black/70 hover:text-black dark:text-white/70 dark:hover:text-white"
          >
            Portfolio
          </Link>
        </nav>

        <div className="ml-auto flex items-center gap-1.5 text-xs text-black/50 dark:text-white/50">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              health === "up" ? "bg-emerald-500" : health === "down" ? "bg-red-500" : "bg-black/20"
            }`}
          />
          API {health === "checking" ? "…" : health}
        </div>
      </div>
    </header>
  );
}
