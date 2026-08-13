const TICKER_PATTERN = /^[A-Z][A-Z0-9.-]{0,9}$/;

export function normalizeTicker(value: string): string | null {
  const normalized = value.trim().toUpperCase();
  return TICKER_PATTERN.test(normalized) ? normalized : null;
}
