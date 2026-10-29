/** Sector comparison table (#43): pure helpers over the daily screen snapshot. */

export const SECTOR_TABLE_CAP = 40;

export type SectorRow = {
  ticker: string;
  name: string | null;
  oe_yield: number | null;
  /** Latest FY OE/sh ÷ price (#59). Absent on snapshots from before that. */
  oe_yield_latest?: number | null;
  oe_yield_cons?: number | null;
  oe_yield_basis?: string | null;
  payback_years: number | null;
  payback_cons?: number | null;
  payback_basis?: string | null;
  ni_margin: number | null;
  ni_margin_latest?: number | null;
  ni_margin_cons?: number | null;
  ni_margin_basis?: string | null;
  debt_to_equity: number | null;
  no_debt: boolean | null;
  debt_state: DebtState;
  /** Null on peers dash rows (#56) that lack metrics. */
  fy: number | null;
  sector: string | null;
  sub_industry: string | null;
  /** Peers table (#56): true for the page ticker. */
  current?: boolean;
  /** Peers table (#56): set when metrics were unavailable. */
  missing?: string | null;
  /** Annual years in the ratio-of-sums window (#58). */
  years?: number | null;
  /** Prior close used for the yields (#59). */
  price?: number | null;
  price_as_of?: string | null;
  /** Why owner earnings is blank when the row still has a price. */
  oe_note?: string | null;
  /** Formula label. "net income (financial)" or null for the OCF formula. */
  oe_basis_note?: string | null;
};

export type PeerSortKey = "oe_yield" | "ni_margin";

export type DebtState = "zero" | "positive" | "unknown" | "n/a";

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

/** Eleven GICS sectors, alphabetical. Order is the site-nav contract (#65). */
export const GICS_SECTORS = [
  "Communication Services",
  "Consumer Discretionary",
  "Consumer Staples",
  "Energy",
  "Financials",
  "Health Care",
  "Industrials",
  "Information Technology",
  "Materials",
  "Real Estate",
  "Utilities",
] as const;

export type SiteNavLink = { label: string; href: string };

export function docsNavLink(): SiteNavLink {
  return { label: "How metrics are calculated", href: "/docs" };
}

/** S&P 500 screen plus the 11 sector comparison pages. */
export function oeComparisonLinks(): SiteNavLink[] {
  return [
    { label: "S&P 500", href: "/screen" },
    ...GICS_SECTORS.map((name) => ({ label: name, href: sectorHref(name) })),
  ];
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

const CONS_NUMBER_KEYS = [
  "oe_yield_latest",
  "oe_yield_cons",
  "payback_cons",
  "ni_margin_latest",
  "ni_margin_cons",
] as const;

const CONS_BASIS_KEYS = ["oe_yield_basis", "payback_basis", "ni_margin_basis"] as const;

/** Copy #59 fields only when the payload has them, so old rows keep the old cells. */
export function optionalConsFields(r: Record<string, unknown>): Partial<SectorRow> {
  const out: Partial<SectorRow> = {};
  for (const key of CONS_NUMBER_KEYS) {
    if (key in r) out[key] = num(r[key]);
  }
  for (const key of CONS_BASIS_KEYS) {
    if (key in r) out[key] = typeof r[key] === "string" ? r[key] : null;
  }
  return out;
}

function metricForSort(row: SectorRow, key: PeerSortKey): number | null {
  if (key === "oe_yield") {
    return row.oe_yield_cons !== undefined ? row.oe_yield_cons : row.oe_yield;
  }
  return row.ni_margin_cons !== undefined ? row.ni_margin_cons : row.ni_margin;
}

function parseDebtState(v: unknown, noDebt: unknown): DebtState {
  if (v === "zero" || v === "positive" || v === "unknown" || v === "n/a") return v;
  // Older seeds without debt_state: fall back to no_debt.
  if (noDebt === true) return "zero";
  if (noDebt === false) return "positive";
  return "unknown";
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
    ...optionalConsFields(r),
    payback_years: num(r.payback_years),
    ni_margin: num(r.ni_margin),
    years: num(r.years),
    debt_to_equity: num(r.debt_to_equity),
    no_debt: typeof r.no_debt === "boolean" ? r.no_debt : null,
    debt_state: parseDebtState(r.debt_state, r.no_debt),
    fy: r.fy as number,
    sector: typeof r.sector === "string" ? r.sector : null,
    sub_industry: typeof r.sub_industry === "string" ? r.sub_industry : null,
    ...priceFields(r),
  };
}

function priceFields(
  r: Record<string, unknown>,
): Pick<SectorRow, "price" | "price_as_of" | "oe_note" | "oe_basis_note"> {
  return {
    price: num(r.price),
    price_as_of: typeof r.price_as_of === "string" && r.price_as_of.trim() ? r.price_as_of.trim() : null,
    oe_note: typeof r.oe_note === "string" && r.oe_note.trim() ? r.oe_note.trim() : null,
    oe_basis_note:
      typeof r.oe_basis_note === "string" && r.oe_basis_note.trim() ? r.oe_basis_note.trim() : null,
  };
}

/**
 * OE yield or NI margin, high to low. Null metrics follow numbers.
 * Dash rows (`missing`) stay last on every key.
 */
export function sortPeerRows<T extends SectorRow>(rows: T[], key: PeerSortKey = "oe_yield"): T[] {
  const dash: T[] = [];
  const rest: T[] = [];
  for (const row of rows) {
    if (row.missing) dash.push(row);
    else rest.push(row);
  }
  const cmp = (a: T, b: T) => {
    const av = metricForSort(a, key);
    const bv = metricForSort(b, key);
    if (av === null || bv === null) {
      if (av !== bv) return av === null ? 1 : -1;
      return a.ticker.localeCompare(b.ticker);
    }
    if (av !== bv) return bv - av;
    return a.ticker.localeCompare(b.ticker);
  };
  rest.sort(cmp);
  dash.sort((a, b) => a.ticker.localeCompare(b.ticker));
  return [...rest, ...dash];
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
  "Price",
  "OE yield",
  "Payback (yrs)",
  "NI margin",
  "Debt / equity",
  "FY",
];

/** Index in sectorCells (headers minus the ticker link). */
function cellIndex(header: string): number {
  const index = SECTOR_TABLE_HEADERS.indexOf(header) - 1;
  if (index < 0) throw new Error(`missing sector header: ${header}`);
  return index;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

const PRICE_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-15" → "Oct 15". Anything else is shown as given. */
export function formatPriceAsOf(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!match) return value.trim();
  const month = PRICE_MONTHS[Number(match[2]) - 1];
  const day = Number(match[3]);
  if (!month || !Number.isInteger(day) || day < 1 || day > 31) return value.trim();
  return `${month} ${day}`;
}

export type PriceCell = {
  /** "$99.09" or "—". */
  amount: string;
  /** Muted suffix, already formatted. Null when there is no date. */
  asOf: string | null;
  /** Set when the amount is a dash. */
  title: string | null;
  /** amount plus suffix, for string comparisons. */
  text: string;
};

function priceMissingTitle(row: SectorRow): string {
  if (row.missing) return row.missing;
  if (row.oe_note) return row.oe_note;
  return "no price in snapshot";
}

export function priceCell(row: SectorRow): PriceCell {
  if (typeof row.price !== "number" || !Number.isFinite(row.price)) {
    return { amount: "—", asOf: null, title: priceMissingTitle(row), text: "—" };
  }
  const amount = `$${row.price.toFixed(2)}`;
  const asOf = row.price_as_of ? formatPriceAsOf(row.price_as_of) : null;
  return { amount, asOf, title: null, text: asOf ? `${amount} ${asOf}` : amount };
}

function withBasis(base: string, basis: string | null | undefined): string {
  return basis ? `${base} ${basis}` : base;
}

function oeYieldCell(row: SectorRow): string {
  if (row.oe_yield_cons !== undefined) return withBasis(pct(row.oe_yield_cons), row.oe_yield_basis);
  const base = pct(row.oe_yield);
  const years = row.years;
  if (typeof years !== "number" || !Number.isFinite(years) || years <= 0) return base;
  return `${base} ${years}y`;
}

function paybackCell(row: SectorRow): string {
  if (row.payback_cons !== undefined) {
    const base = row.payback_cons === null ? "—" : row.payback_cons.toFixed(1);
    return withBasis(base, row.payback_basis);
  }
  return row.payback_years === null ? "—" : row.payback_years.toFixed(1);
}

function marginCell(row: SectorRow): string {
  if (row.ni_margin_cons !== undefined) return withBasis(pct(row.ni_margin_cons), row.ni_margin_basis);
  return pct(row.ni_margin);
}

/** Display cells after the ticker link, in header order (minus Ticker). */
export function sectorCells(row: SectorRow): string[] {
  return [
    row.name ?? "—",
    priceCell(row).text,
    oeYieldCell(row),
    paybackCell(row),
    marginCell(row),
    debtCell(row).text,
    row.fy === null ? "—" : String(row.fy),
  ];
}

/** Index of the price cell in sectorCells. */
export const PRICE_CELL_INDEX = cellIndex("Price");

/** Index of the OE yield cell in sectorCells. */
export const OE_YIELD_CELL_INDEX = cellIndex("OE yield");

/** Index of the D/E cell in sectorCells (for the tooltip wrapper). */
export const DEBT_CELL_INDEX = cellIndex("Debt / equity");

export const DEBT_TOOLTIP_NA =
  "Not meaningful for financials: debt is a bank's or insurer's raw material, so D/E is not shown.";
export const DEBT_TOOLTIP_UNKNOWN = "Debt unknown: the latest 10-K has no debt total or component we can read.";
export const DEBT_TOOLTIP_NO_EQUITY = "Has debt, but equity is zero or negative, so D/E is not meaningful.";

/**
 * Debt / equity cell (#51). "0 (no debt)" only with evidence of no debt
 * (debt_state "zero", per the existing debt rules); the ratio when there is
 * debt; "—" with a tooltip saying why when unknown or n/a.
 */
export function debtCell(row: SectorRow): { text: string; title: string | null } {
  switch (row.debt_state) {
    case "zero":
      return { text: "0 (no debt)", title: "The latest 10-K reports zero debt." };
    case "n/a":
      return { text: "—", title: DEBT_TOOLTIP_NA };
    case "positive":
      return row.debt_to_equity === null
        ? { text: "—", title: DEBT_TOOLTIP_NO_EQUITY }
        : { text: row.debt_to_equity.toFixed(2), title: null };
    default:
      return { text: "—", title: DEBT_TOOLTIP_UNKNOWN };
  }
}

export function groupHeading(g: SectorGroup): string {
  const kind = g.level === "sector" ? "GICS sector" : "GICS sub-industry";
  return `${g.name} (${kind}) · S&P 500, by OE yield`;
}

/** Ticker page names the GICS universe. Standalone /sector pages keep groupHeading. */
export function sectorTableHeading(kind: "ticker" | "slug", g: SectorGroup): string {
  if (kind === "ticker") return `S&P 500 peers — ${g.name}`;
  return groupHeading(g);
}

/** Count plus snapshot price date. Widen stays a separate link; there is no Open table link. */
export function sectorTableNote(g: SectorGroup, priceAsOf: string | null): string {
  const price = priceAsOf
    ? ` · daily snapshot, prices as of ${priceAsOf}`
    : " · daily snapshot";
  return `${groupCountNote(g)}${price}`;
}

export function groupCountNote(g: SectorGroup): string {
  return g.total > g.rows.length
    ? `Top ${g.rows.length} of ${g.total} names`
    : `${g.total} name${g.total === 1 ? "" : "s"}`;
}
