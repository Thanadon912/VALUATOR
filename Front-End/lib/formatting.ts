export function formatCurrency(
  value: number | string | undefined | null,
  currency: string = "USD"
): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
    notation: Math.abs(num) >= 1_000_000 ? "compact" : "standard",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

export function formatTimestamp(timestamp: string | number | undefined | null): string {
  if (timestamp == null || timestamp === "") return "—";
  
  if (typeof timestamp === "string" && timestamp.includes("-")) {
    try {
      const date = new Date(timestamp);
      if (!isNaN(date.getTime())) {
        return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
      }
    } catch {
      return timestamp;
    }
  }

  const num = typeof timestamp === "string" ? parseInt(timestamp, 10) : timestamp;
  if (isNaN(num)) return typeof timestamp === "string" ? timestamp : "—";

  const ms = num < 10000000000 ? num * 1000 : num;
  const date = new Date(ms);
  
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short"
  }).format(date);
}

export function formatPercent(
  value: number | string | undefined | null,
  forceSign = false
): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";

  const sign = forceSign && num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}%`;
}

export function formatNumber(value: number | string | undefined | null): string {
  if (value == null || value === "") return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  
  if (Math.abs(num) >= 1_000_000_000_000) return `${(num / 1_000_000_000_000).toFixed(2)}T`;
  if (Math.abs(num) >= 1_000_000_000) return `${(num / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(num) >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;

  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

export function formatChange(value: number | undefined | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}
