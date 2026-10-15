export type PeerItem = {
  ticker: string;
  name?: string | null;
  /** SEC SIC peers (#54) only: latest annual revenue in USD and its year. */
  revenue?: number | null;
  revenue_fy?: number | null;
};

export type PeersBlock = {
  /** sub_industry / industry_group: S&P 500 by GICS (#42). sic / sic3: non-S&P by SEC SIC (#54). */
  basis: "sub_industry" | "industry_group" | "sic" | "sic3";
  group: string;
  sub_industry: string;
  fallback: boolean;
  total: number;
  peers: PeerItem[];
  sic?: number | null;
  reason?: string | null;
};

function sicLabel(block: PeersBlock): string {
  const name = block.sub_industry || "this industry";
  return block.sic != null ? `${name} (SIC ${block.sic})` : name;
}

/** Heading for the ticker-page peers section. Null when there is nothing to list. */
export function peersHeading(block: PeersBlock | null | undefined): string | null {
  if (!block) return null;
  if (block.basis === "sic" || block.basis === "sic3") {
    if (block.peers.length === 0) return block.reason ? "Peers (same SEC industry)" : null;
    if (block.basis === "sic") {
      return `Peers in the same SEC industry: ${sicLabel(block)}, by latest annual revenue`;
    }
    return `Peers in the same SEC industry group ${block.group} (fewer than 5 others in ${sicLabel(block)}), by latest annual revenue`;
  }
  if (block.peers.length === 0) return null;
  if (block.basis === "sub_industry") {
    return `S&P 500 peers in ${block.sub_industry} (GICS sub-industry)`;
  }
  return `S&P 500 peers in the ${block.group} industry group (fewer than 3 others in ${block.sub_industry})`;
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
