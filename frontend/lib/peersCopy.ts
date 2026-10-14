export type PeerItem = { ticker: string; name?: string | null };

export type PeersBlock = {
  basis: "sub_industry" | "industry_group";
  group: string;
  sub_industry: string;
  fallback: boolean;
  total: number;
  peers: PeerItem[];
};

/** Heading for the ticker-page peers section. Null when there is nothing to list. */
export function peersHeading(block: PeersBlock | null | undefined): string | null {
  if (!block || block.peers.length === 0) return null;
  if (block.basis === "sub_industry") {
    return `S&P 500 peers in ${block.sub_industry} (GICS sub-industry)`;
  }
  return `S&P 500 peers in the ${block.group} industry group (fewer than 3 others in ${block.sub_industry})`;
}

/** "+N more" note when the list was capped. */
export function peersMore(block: PeersBlock | null | undefined): string | null {
  if (!block) return null;
  const extra = block.total - block.peers.length;
  return extra > 0 ? `+${extra} more` : null;
}
