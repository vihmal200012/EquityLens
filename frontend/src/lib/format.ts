export function fmtCurrency(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtBigNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(2)}K`;
  return fmtCurrency(value);
}

/**
 * The backend denominates every financial-statement and valuation dollar
 * figure (revenue, market cap, DCF enterprise/equity value, FCF, etc.) in
 * millions of dollars — see docs/FINANCIAL_MODEL.md and
 * backend/providers/mock_provider.py. Per-share figures (price, EPS,
 * implied share price) are plain dollars and must NOT go through this
 * function. Route every millions-denominated value through here instead of
 * fmtBigNumber/fmtCurrency directly, so the unit assumption is explicit at
 * every call site and can't silently drift out of sync again.
 */
export function fmtMoneyFromMillions(valueInMillions: number | null | undefined): string {
  if (valueInMillions === null || valueInMillions === undefined || Number.isNaN(valueInMillions)) return "—";
  return fmtBigNumber(valueInMillions * 1e6);
}

/**
 * Share counts from the backend are likewise expressed in millions of
 * shares, but are not a dollar amount — never format them as currency.
 */
export function fmtSharesFromMillions(valueInMillions: number | null | undefined): string {
  if (valueInMillions === null || valueInMillions === undefined || Number.isNaN(valueInMillions)) return "—";
  return fmtNumber(valueInMillions * 1e6, 0);
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function titleCase(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
