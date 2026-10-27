import type { DebtState, SectorRow } from "./sectorTable";

export type PeerItem = {
  ticker: string;
  name?: string | null;
  /** SEC SIC peers (#54) only: latest annual revenue in USD and its year. */
  revenue?: number | null;
  revenue_fy?: number | null;
};

/** Peers comparison row (#56): sector columns plus current/missing. */
export type PeerRow = SectorRow;

export type PeersBlock = {
  /** sub_industry / industry_group: S&P 500 by GICS (#42). sic / sic3: non-S&P by SEC SIC (#54). */
  basis: "sub_industry" | "industry_group" | "sic" | "sic3";
  group: string;
  sub_industry: string;
  fallback: boolean;
  total: number;
  peers: PeerItem[];
  /** Comparison table rows: current ticker first, then peers (#56). */
  rows?: PeerRow[];
  sic?: number | null;
  reason?: string | null;
};

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

function optionalCons(r: Record<string, unknown>): Partial<SectorRow> {
  const out: Partial<SectorRow> = {};
  for (const key of CONS_NUMBER_KEYS) {
    if (key in r) out[key] = num(r[key]);
  }
  for (const key of CONS_BASIS_KEYS) {
    if (key in r) out[key] = typeof r[key] === "string" ? r[key] : null;
  }
  return out;
}

function parseDebtState(v: unknown, noDebt: unknown): DebtState {
  if (v === "zero" || v === "positive" || v === "unknown" || v === "n/a") return v;
  if (noDebt === true) return "zero";
  if (noDebt === false) return "positive";
  return "unknown";
}

/**
 * Tolerant peer-row parse (#56). Keeps dash rows (null fy / metrics) so a
 * missing ticker still appears in the table.
 */
export function parsePeerRow(value: unknown): PeerRow | null {
  if (typeof value !== "object" || value === null) return null;
  const r = value as Record<string, unknown>;
  if (typeof r.ticker !== "string" || !r.ticker.trim()) return null;
  const fyRaw = r.fy;
  const fy = fyRaw === null || fyRaw === undefined ? null : num(fyRaw);
  return {
    ticker: r.ticker.toUpperCase(),
    name: typeof r.name === "string" ? r.name : null,
    oe_yield: num(r.oe_yield),
    ...optionalCons(r),
    payback_years: num(r.payback_years),
    ni_margin: num(r.ni_margin),
    years: num(r.years),
    debt_to_equity: num(r.debt_to_equity),
    no_debt: typeof r.no_debt === "boolean" ? r.no_debt : null,
    debt_state: parseDebtState(r.debt_state, r.no_debt),
    fy,
    sector: typeof r.sector === "string" ? r.sector : null,
    sub_industry: typeof r.sub_industry === "string" ? r.sub_industry : null,
    current: r.current === true,
    missing: typeof r.missing === "string" ? r.missing : null,
    price: num(r.price),
    price_as_of: typeof r.price_as_of === "string" && r.price_as_of.trim() ? r.price_as_of.trim() : null,
    oe_note: typeof r.oe_note === "string" && r.oe_note.trim() ? r.oe_note.trim() : null,
  };
}

/** 3-digit SIC digits from a widened group such as "SIC 565x" or "565". */
function sic3Digits(block: PeersBlock): string {
  const match = String(block.group).match(/(\d{3})/);
  return match ? match[1] : block.group;
}

/** Heading for the ticker-page peers section. Null when there is nothing to list. */
export function peersHeading(block: PeersBlock | null | undefined): string | null {
  if (!block) return null;
  if (block.basis === "sic" || block.basis === "sic3") {
    if (block.peers.length === 0) return block.reason ? "Industry peers — all US filers" : null;
    if (block.basis === "sic") {
      return block.sic != null
        ? `Industry peers — all US filers (SIC ${block.sic} ${block.sub_industry})`
        : `Industry peers — all US filers (${block.sub_industry})`;
    }
    return `Industry peers — all US filers (SIC ${sic3Digits(block)}xx, widened from SIC ${block.sic} ${block.sub_industry})`;
  }
  if (block.peers.length === 0) return null;
  if (block.basis === "sub_industry") {
    return `S&P 500 peers in ${block.sub_industry} (GICS sub-industry)`;
  }
  return `S&P 500 peers in the ${block.group} industry group (fewer than 3 others in ${block.sub_industry})`;
}

/** One-line subhead under the SEC SIC peers heading. Null when the list is empty. */
export function peersNote(block: PeersBlock | null | undefined): string | null {
  if (!block || block.peers.length === 0) return null;
  if (block.basis === "sic") {
    return `Top ${block.peers.length} of ${block.total} US SEC filers in SIC ${block.sic} with annual revenue of at least $10M, ranked by latest revenue and sorted by OE yield.`;
  }
  if (block.basis === "sic3") {
    return `Fewer than 5 peers in SIC ${block.sic} cleared $10M revenue; widened to ${block.peers.length} of ${block.total} US SEC filers in the 3-digit SIC ${sic3Digits(block)} group, sorted by OE yield.`;
  }
  return null;
}

/** Why the SIC peer list is blank (e.g. no peer reports revenue). */
export function peersReason(block: PeersBlock | null | undefined): string | null {
  if (!block || block.peers.length > 0) return null;
  return block.reason ? `No peers listed: ${block.reason}.` : null;
}

/** Compact revenue, e.g. 10588000000 -> "$10.6B". */
export function peerRevenue(peer: PeerItem): string | null {
  const v = peer.revenue;
  if (typeof v !== "number" || !Number.isFinite(v) || v <= 0) return null;
  const fy = peer.revenue_fy ? ` FY${peer.revenue_fy}` : "";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B${fy}`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M${fy}`;
  return `$${Math.round(v / 1e3)}K${fy}`;
}

/** "+N more" note when the list was capped. */
export function peersMore(block: PeersBlock | null | undefined): string | null {
  if (!block) return null;
  const extra = block.total - block.peers.length;
  return extra > 0 ? `+${extra} more` : null;
}
