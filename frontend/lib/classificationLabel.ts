export type ClassificationBlock = {
  scheme: "gics" | "sic";
  sector?: string | null;
  industry?: string | null;
  sic?: number | null;
  sic_description?: string | null;
  link?: string | null;
};

/** Visible label for the ticker-page classification link. */
export function classificationLabel(
  block: ClassificationBlock | null | undefined,
): string | null {
  if (!block) return null;
  if (block.scheme === "gics") {
    if (!block.sector) return null;
    return block.industry ? `${block.sector} · ${block.industry}` : block.sector;
  }
  if (block.scheme === "sic") {
    const sicPart =
      block.sic != null
        ? block.industry
          ? `${block.industry} (SIC ${block.sic})`
          : `SIC ${block.sic}`
        : block.industry ?? null;
    if (!sicPart) return null;
    return block.sector ? `${block.sector} · ${sicPart}` : sicPart;
  }
  return null;
}

export function classificationSchemeLabel(
  block: ClassificationBlock | null | undefined,
): string | null {
  if (!block) return null;
  if (block.scheme === "gics") return "GICS";
  if (block.scheme === "sic") return "SEC SIC";
  return null;
}
