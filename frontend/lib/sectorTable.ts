/** Sector comparison table (#43): pure helpers over the daily screen snapshot. */

export const SECTOR_TABLE_CAP = 40;

export type SectorRow = {
  ticker: string;
  name: string | null;
  oe_yield: number | null;
  payback_years: number | null;
  ni_to_equity: number | null;
  debt_to_equity: number | null;
  no_debt: boolean | null;
  fy: number;
  sector: string | null;
  sub_industry: string | null;
};

export type SectorLevel = "sub_industry" | "sector";

export type SectorGroup = {
  level: SectorLevel;
  name: string;
  /** Parent sector (same as name for level "sector"). */
  sector: string | null;
  total: number;
  rows: SectorRow[];
};

/** URL slug: "Technology Hardware, Storage & Peripherals" → "technology-hardware-storage-and-peripherals". */
export function sectorSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function sectorHref(name: string): string {
  return `/sector/${sectorSlug(name)}`;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Parse one snapshot row; null when the row lacks the always-present fields. */
export function parseSectorRow(value: unknown): SectorRow | null {
  if (typeof value !== "object" || value === null) return null;
  const r = value as Record<string, unknown>;
  if (typeof r.ticker !== "string" || num(r.fy) === null) return null;
  return {
    ticker: r.ticker.toUpperCase(),
    name: typeof r.name === "string" ? r.name : null,
    oe_yield: num(r.oe_yield),
    payback_years: num(r.payback_years),
    ni_to_equity: num(r.ni_to_equity),
    debt_to_equity: num(r.debt_to_equity),
    no_debt: typeof r.no_debt === "boolean" ? r.no_debt : null,
    fy: r.fy as number,
    sector: typeof r.sector === "string" ? r.sector : null,
    sub_industry: typeof r.sub_industry === "string" ? r.sub_industry : null,
  };
}

/** OE yield high to low; blank OE yields (#52) last, by ticker. */
export function byOeYield(a: SectorRow, b: SectorRow): number {
  if (a.oe_yield === null || b.oe_yield === null) {
    if (a.oe_yield !== b.oe_yield) return a.oe_yield === null ? 1 : -1;
    return a.ticker.localeCompare(b.ticker);
  }
  return b.oe_yield - a.oe_yield;
}

/**
 * Rows of one group, sorted by OE yield (highest first), capped. A capped
 * group still includes `keep` (the ticker page's own row) in place of the
 * last row when it would fall below the cap.
 */
export function groupRows(
  rows: SectorRow[],
  level: SectorLevel,
  name: string,
  cap: number = SECTOR_TABLE_CAP,
  keep: string | null = null,
): SectorGroup {
  const members = rows
    .filter((r) => (level === "sector" ? r.sector : r.sub_industry) === name)
    .sort(byOeYield);
  const sector = level === "sector" ? name : (members[0]?.sector ?? null);
  let shown = members.slice(0, cap);
  const own = keep ? members.find((r) => r.ticker === keep.toUpperCase()) : undefined;
  if (own && !shown.includes(own) && shown.length > 0) shown = [...shown.slice(0, -1), own];
  return { level, name, sector, total: members.length, rows: shown };
}

/** Resolve a /sector/{slug}: sub-industry first, then sector. */
export function resolveSlug(rows: SectorRow[], slug: string): SectorGroup | null {
  const want = slug.toLowerCase();
  const sub = rows.find((r) => r.sub_industry && sectorSlug(r.sub_industry) === want);
  // Standalone pages list the whole group (Financials has ~70 names).
  if (sub?.sub_industry) return groupRows(rows, "sub_industry", sub.sub_industry, Infinity);
  const sec = rows.find((r) => r.sector && sectorSlug(r.sector) === want);
  if (sec?.sector) return groupRows(rows, "sector", sec.sector, Infinity);
  return null;
}

/** Group for a ticker page: its sub-industry, falling back to sector when the row is missing. */
export function groupForTicker(
  rows: SectorRow[],
  ticker: string,
  subIndustry: string | null,
  sector: string | null,
): SectorGroup | null {
  const own = rows.find((r) => r.ticker === ticker.toUpperCase());
  const sub = own?.sub_industry ?? subIndustry;
  if (sub) {
    const g = groupRows(rows, "sub_industry", sub, SECTOR_TABLE_CAP, ticker);
    if (g.total > 0) return g;
  }
  const sec = own?.sector ?? sector;
  return sec ? groupRows(rows, "sector", sec, SECTOR_TABLE_CAP, ticker) : null;
}

export const SECTOR_TABLE_HEADERS = [
  "Ticker",
  "Name",
  "OE yield",
  "Payback (yrs)",
  "NI / equity",
  "Debt / equity",
  "No debt",
  "FY",
];

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

/** Display cells after the ticker link, in header order (minus Ticker). */
export function sectorCells(row: SectorRow): string[] {
  return [
    row.name ?? "—",
    pct(row.oe_yield),
    row.payback_years === null ? "—" : row.payback_years.toFixed(1),
    pct(row.ni_to_equity),
    row.debt_to_equity === null ? "—" : row.debt_to_equity.toFixed(2),
    row.no_debt === null ? "—" : row.no_debt ? "Yes" : "No",
    String(row.fy),
  ];
}

export function groupHeading(g: SectorGroup): string {
  const kind = g.level === "sector" ? "GICS sector" : "GICS sub-industry";
  return `${g.name} (${kind}) · S&P 500, by OE yield`;
}

export function groupCountNote(g: SectorGroup): string {
  return g.total > g.rows.length
    ? `Top ${g.rows.length} of ${g.total} names`
    : `${g.total} name${g.total === 1 ? "" : "s"}`;
}
