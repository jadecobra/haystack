import { sectorHref } from "./sectorTable.ts";

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
