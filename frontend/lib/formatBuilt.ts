/**
 * Format a Built-at ISO instant for on-page display.
 * Always UTC (SSR and client must match; never local/Chicago).
 */

function ordinal(day: number): string {
  const mod100 = day % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${day}th`;
  switch (day % 10) {
    case 1:
      return `${day}st`;
    case 2:
      return `${day}nd`;
    case 3:
      return `${day}rd`;
    default:
      return `${day}th`;
  }
}

/**
 * Human-readable UTC stamp: `Sunday, October 4th 2026 at 03:20 UTC`.
 * Invalid/missing input: returns the raw string when present, otherwise `—`.
 */
export function formatBuiltTimestamp(
  value: string | null | undefined,
): string {
  if (value == null || value === "") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const weekday = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    timeZone: "UTC",
  }).format(date);
  const month = new Intl.DateTimeFormat("en-US", {
    month: "long",
    timeZone: "UTC",
  }).format(date);
  const day = date.getUTCDate();
  const year = date.getUTCFullYear();
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");

  return `${weekday}, ${month} ${ordinal(day)} ${year} at ${hh}:${mm} UTC`;
}

/** Full on-page label including the `Built ` prefix. */
export function formatBuiltLabel(value: string | null | undefined): string {
  return `Built ${formatBuiltTimestamp(value)}`;
}

/** Exported for unit tests. */
export function dayOrdinal(day: number): string {
  return ordinal(day);
}
