import { LOCKED_LABELS, type LockedLabel } from "./locked-labels";

export type { LockedLabel };

export type FormatKind = "pct" | "yield" | "shares" | "money";

export type MetricDocDraft = {
  label: LockedLabel;
  formula: string;
  meaning: string;
  format: FormatKind;
};

export type PrimerBlock = {
  id:
    | "owner-earnings"
    | "sources"
    | "table-contract"
    | "dgs30-clocks"
    | "last-close";
  heading: string;
  body: string;
};

export type DocsModel = {
  title: string;
  primer: PrimerBlock[];
  entries: Array<{
    label: LockedLabel;
    anchor: string;
    formula: string;
    meaning: string;
    formatKind: FormatKind;
    formatNote: string;
  }>;
};

const FORMAT_NOTES: Record<FormatKind, string> = {
  pct: "Backend shows one decimal percent (for example 12.3%). Missing values are an em dash.",
  yield:
    "Backend shows two decimal percent (for example 4.35%). Missing values are an em dash.",
  shares:
    "Backend shows share counts with B/M suffixes or comma grouping. Missing values are an em dash.",
  money:
    "Backend shows a dollar amount with B/M scaling when large. Missing values are an em dash.",
};

const PRIMER: PrimerBlock[] = [
  {
    id: "owner-earnings",
    heading: "Owner earnings",
    body: "Owner earnings (OE) is cash after maintenance reinvestment, before allocation. OE = OCF − min(|capex|, |D&A|). OCF is the reported operating-cash tag when present. If missing, OCF = ΔCash − CFI − CFF − FX (FX = 0 if absent). If still missing, OCF = NI + D&A − ΔNWC using AR, inventory, and AP pairs that exist in both the year and the prior year. Capex is PPE (or the combined PPE+intangibles tag when present), plus capitalized software, without double-counting ProductiveAssets on top of PPE. If OCF cannot be resolved, or both capex and D&A are missing, owner earnings is null.",
  },
  {
    id: "sources",
    heading: "Sources",
    body: "SEC companyfacts JSON supplies US-GAAP FY series tied to 10-K filings for the last five years. FRED series DGS30 supplies the 30-year Treasury yield. Previous close comes from Yahoo, then NASDAQ.",
  },
  {
    id: "table-contract",
    heading: "Table contract",
    body: "Row names and order are LOCKED_LABELS from the backend contract. Display strings in the Analyze table come from the backend. This page explains the formulas. It does not recompute them.",
  },
  {
    id: "dgs30-clocks",
    heading: "Two DGS30 clocks",
    body: "The table row 30 Year Treasury (DGS30) uses the year-end observation for each calendar year column. The subtitle under Owner Earnings / 30 Year Treasury per Share uses the latest daily DGS30 print. That treasury ratio is OE per share divided by the DGS30 decimal yield, and the backend formats it as dollars, not as a percent.",
  },
  {
    id: "last-close",
    heading: "Last close price",
    body: "Owner Earnings / Last Close Price uses the same previous close on every year column. The close is not a per-year historical price.",
  },
];

const CATALOG: MetricDocDraft[] = [
  {
    label: "Net Income / Revenue",
    formula: "Net Income ÷ Revenue",
    meaning: "Profit margin on sales for the fiscal year.",
    format: "pct",
  },
  {
    label: "Net Income / Equity",
    formula: "Net Income ÷ Equity",
    meaning: "Return on book equity.",
    format: "pct",
  },
  {
    label: "Net Income / Assets",
    formula: "Net Income ÷ Assets",
    meaning: "Return on total assets.",
    format: "pct",
  },
  {
    label: "Net Income / Total Liabilities",
    formula: "Net Income ÷ Total Liabilities",
    meaning: "Net income relative to all liabilities.",
    format: "pct",
  },
  {
    label: "Net Income / Debt",
    formula: "Net Income ÷ Debt",
    meaning: "Net income relative to interest-bearing debt.",
    format: "pct",
  },
  {
    label: "Owner Earnings / Revenue",
    formula: "Owner Earnings ÷ Revenue",
    meaning: "Owner earnings as a share of sales.",
    format: "pct",
  },
  {
    label: "Owner Earnings / Equity",
    formula: "Owner Earnings ÷ Equity",
    meaning: "Owner earnings relative to book equity.",
    format: "pct",
  },
  {
    label: "Owner Earnings / Assets",
    formula: "Owner Earnings ÷ Assets",
    meaning: "Owner earnings relative to total assets.",
    format: "pct",
  },
  {
    label: "Owner Earnings / Total Liabilities",
    formula: "Owner Earnings ÷ Total Liabilities",
    meaning: "Owner earnings relative to all liabilities.",
    format: "pct",
  },
  {
    label: "Owner Earnings / Debt",
    formula: "Owner Earnings ÷ Debt",
    meaning: "Owner earnings relative to interest-bearing debt.",
    format: "pct",
  },
  {
    label: "Owner Earnings / Last Close Price",
    formula: "(Owner Earnings ÷ Shares) ÷ Last Close Price",
    meaning:
      "Owner earnings per share divided by the shared previous close used on every year column.",
    format: "yield",
  },
  {
    label: "Dividends / Net Income",
    formula: "Dividends ÷ Net Income",
    meaning: "Share of net income paid as dividends.",
    format: "pct",
  },
  {
    label: "Dividends / Owner Earnings",
    formula: "Dividends ÷ Owner Earnings",
    meaning: "Share of owner earnings paid as dividends.",
    format: "pct",
  },
  {
    label: "Dividends / Equity",
    formula: "Dividends ÷ Equity",
    meaning: "Dividend payout relative to book equity.",
    format: "pct",
  },
  {
    label: "Shares Outstanding",
    formula: "Shares Outstanding",
    meaning: "Common shares used as the per-share denominator.",
    format: "shares",
  },
  {
    label: "Debt per Share",
    formula: "Debt ÷ Shares",
    meaning: "Interest-bearing debt on a per-share basis.",
    format: "money",
  },
  {
    label: "Revenue per Share",
    formula: "Revenue ÷ Shares",
    meaning: "Sales on a per-share basis.",
    format: "money",
  },
  {
    label: "Net Income per Share",
    formula: "Net Income ÷ Shares",
    meaning: "Reported earnings on a per-share basis.",
    format: "money",
  },
  {
    label: "Owner Earnings per Share",
    formula: "Owner Earnings ÷ Shares",
    meaning: "Owner earnings on a per-share basis.",
    format: "money",
  },
  {
    label: "Dividends per Share",
    formula: "Dividends ÷ Shares",
    meaning: "Cash dividends on a per-share basis.",
    format: "money",
  },
  {
    label: "Equity per Share",
    formula: "Equity ÷ Shares",
    meaning: "Book equity on a per-share basis.",
    format: "money",
  },
  {
    label: "Assets per Share",
    formula: "Assets ÷ Shares",
    meaning: "Total assets on a per-share basis.",
    format: "money",
  },
  {
    label: "Cash per Share",
    formula: "Cash ÷ Shares",
    meaning: "Cash and cash equivalents on a per-share basis.",
    format: "money",
  },
  {
    label: "Liabilities per Share",
    formula: "Total Liabilities ÷ Shares",
    meaning: "Total liabilities on a per-share basis.",
    format: "money",
  },
  {
    label: "Owner Earnings / 30 Year Treasury per Share",
    formula: "(Owner Earnings ÷ Shares) ÷ DGS30_decimal",
    meaning:
      "Owner earnings per share divided by that year’s DGS30 decimal yield. The result is dollars of OE per share per unit of yield, not a percent.",
    format: "money",
  },
  {
    label: "30 Year Treasury (DGS30)",
    formula: "Year-end DGS30 (decimal)",
    meaning:
      "FRED 30-year Treasury yield for the calendar year column, stored as a decimal fraction.",
    format: "yield",
  },
];

function labelAnchor(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function resolveDocsModel(
  lockedLabels: readonly string[],
): DocsModel {
  const catalogLabels = CATALOG.map((entry) => entry.label);
  if (
    catalogLabels.length !== lockedLabels.length ||
    catalogLabels.some((label, i) => label !== lockedLabels[i])
  ) {
    throw new Error(
      "metrics catalog labels drifted from locked labels (order or contents)",
    );
  }

  return {
    title: "How metrics are calculated",
    primer: PRIMER,
    entries: CATALOG.map((entry) => ({
      label: entry.label,
      anchor: labelAnchor(entry.label),
      formula: entry.formula,
      meaning: entry.meaning,
      formatKind: entry.format,
      formatNote: FORMAT_NOTES[entry.format],
    })),
  };
}

export { LOCKED_LABELS };
