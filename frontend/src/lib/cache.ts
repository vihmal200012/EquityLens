// Lightweight per-ticker cache so results computed on one tab (DCF,
// scenarios, comparables) can be picked up by the Report tab, matching the
// backend's POST /report contract (it accepts whatever the caller already
// computed rather than recomputing it). Session-only by design.

function keyFor(ticker: string, key: string): string {
  return `equitylens:${ticker.toUpperCase()}:${key}`;
}

export function getCached<T>(ticker: string, key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(keyFor(ticker, key));
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function setCached<T>(ticker: string, key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(keyFor(ticker, key), JSON.stringify(value));
  } catch {
    // storage full or unavailable; silently skip caching
  }
}
