import { LOCKED_LABELS, type LockedLabel } from "./locked-labels";

export type { LockedLabel };

export type MetricDocDraft = {
  label: LockedLabel;
  formula: string;
  meaning: string;
};

export type PrimerBlock = {
  id: "owner-earnings" | "sources" | "last-close";
  heading: string;
  items: string[];
};

export type DocsModel = {
  title: string;
  primer: PrimerBlock[];
  entries: Array<{
    label: LockedLabel;
    anchor: string;
    formula: string;
    meaning: string;
  }>;
};

const PRIMER: PrimerBlock[] = [
  {
    id: "owner-earnings",
    heading: "Owner earnings",
    items: [
      "Owner earnings is the cash left after the company pays to keep the business running.",
      "We start with cash from day-to-day operations.",
      "We subtract maintenance spending. That is the smaller of new plant and equipment spend and the wear-and-tear charge on existing assets.",
      "What remains can be paid to owners, used to grow, or held as cash.",
      "If we cannot find operating cash, or we cannot estimate maintenance, that year is blank.",
    ],
  },
  {
    id: "sources",
    heading: "Sources",
    items: [
      "Company figures come from the U.S. Securities and Exchange Commission Electronic Data Gathering, Analysis, and Retrieval system (EDGAR) annual 10-K filings, using United States Generally Accepted Accounting Principles (US-GAAP).",
      "The 30-year Treasury yield comes from Federal Reserve Economic Data (FRED).",
      "The last close price comes from Yahoo Finance, then the NASDAQ Stock Market (NASDAQ).",
    ],
  },
  {
    id: "last-close",
    heading: "Last close price",
    items: [
      "Last close is the most recent closing share price.",
      "Rows that need a price use this one number for every year in the table.",
      "It is not each year's historical year-end price.",
    ],
  },
];

const CATALOG: MetricDocDraft[] = [
  {
    label: "Owner Earnings / Last Close Price",
    formula: "(Owner Earnings ÷ Shares) ÷ Last Close Price",
    meaning: "Owner earnings per share compared with the latest closing share price.",
  },
  {
    label: "Cash per Share / Last Close Price",
    formula: "(Cash ÷ Shares) ÷ Last Close Price",
    meaning: "Cash per share compared with the latest closing share price.",
  },
  {
    label: "Dividends per Share / Last Close Price",
    formula: "(Dividends ÷ Shares) ÷ Last Close Price",
    meaning: "Dividends per share compared with the latest closing share price.",
  },
  {
    label: "Net Income per Share / Last Close Price",
    formula: "(Net Income ÷ Shares) ÷ Last Close Price",
    meaning: "Net income per share compared with the latest closing share price.",
  },
  {
    label: "Equity per Share / Last Close Price",
    formula: "(Equity ÷ Shares) ÷ Last Close Price",
    meaning: "Book equity per share compared with the latest closing share price.",
  },
  {
    label: "Assets per Share / Last Close Price",
    formula: "(Assets ÷ Shares) ÷ Last Close Price",
    meaning: "Assets per share compared with the latest closing share price.",
  },
  {
    label: "Revenue per Share / Last Close Price",
    formula: "(Revenue ÷ Shares) ÷ Last Close Price",
    meaning: "Revenue per share compared with the latest closing share price.",
  },
  {
    label: "Net Income / Equity",
    formula: "Net Income ÷ Equity",
    meaning: "Return on book equity.",
  },
  {
    label: "Net Income / Assets",
    formula: "Net Income ÷ Assets",
    meaning: "Return on total assets.",
  },
  {
    label: "Net Income / Revenue",
    formula: "Net Income ÷ Revenue",
    meaning: "Profit margin on sales for the fiscal year.",
  },
  {
    label: "Net Income / Total Liabilities",
    formula: "Net Income ÷ Total Liabilities",
    meaning: "Net income relative to all liabilities.",
  },
  {
    label: "Net Income / Debt",
    formula: "Net Income ÷ Debt",
    meaning: "Net income relative to interest-bearing debt.",
  },
  {
    label: "Owner Earnings / Equity",
    formula: "Owner Earnings ÷ Equity",
    meaning: "Owner earnings relative to book equity.",
  },
  {
    label: "Owner Earnings / Assets",
    formula: "Owner Earnings ÷ Assets",
    meaning: "Owner earnings relative to total assets.",
  },
  {
    label: "Owner Earnings / Revenue",
    formula: "Owner Earnings ÷ Revenue",
    meaning: "Owner earnings as a share of sales.",
  },
  {
    label: "Owner Earnings / Total Liabilities",
    formula: "Owner Earnings ÷ Total Liabilities",
    meaning: "Owner earnings relative to all liabilities.",
  },
  {
    label: "Owner Earnings / Debt",
    formula: "Owner Earnings ÷ Debt",
    meaning: "Owner earnings relative to interest-bearing debt.",
  },
  {
    label: "Dividends / Equity",
    formula: "Dividends ÷ Equity",
    meaning: "Dividend payout relative to book equity.",
  },
  {
    label: "Dividends / Owner Earnings",
    formula: "Dividends ÷ Owner Earnings",
    meaning: "Share of owner earnings paid as dividends.",
  },
  {
    label: "Dividends / Net Income",
    formula: "Dividends ÷ Net Income",
    meaning: "Share of net income paid as dividends.",
  },
  {
    label: "Owner Earnings per Share",
    formula: "Owner Earnings ÷ Shares",
    meaning: "Owner earnings on a per-share basis.",
  },
  {
    label: "Cash per Share",
    formula: "Cash ÷ Shares",
    meaning: "Cash and cash equivalents on a per-share basis.",
  },
  {
    label: "Dividends per Share",
    formula: "Dividends ÷ Shares",
    meaning: "Cash dividends on a per-share basis.",
  },
  {
    label: "Net Income per Share",
    formula: "Net Income ÷ Shares",
    meaning: "Reported earnings on a per-share basis.",
  },
  {
    label: "Equity per Share",
    formula: "Equity ÷ Shares",
    meaning: "Book equity on a per-share basis.",
  },
  {
    label: "Assets per Share",
    formula: "Assets ÷ Shares",
    meaning: "Total assets on a per-share basis.",
  },
  {
    label: "Revenue per Share",
    formula: "Revenue ÷ Shares",
    meaning: "Sales on a per-share basis.",
  },
  {
    label: "Liabilities per Share",
    formula: "Total Liabilities ÷ Shares",
    meaning: "Total liabilities on a per-share basis.",
  },
  {
    label: "Debt per Share",
    formula: "Debt ÷ Shares",
    meaning: "Interest-bearing debt on a per-share basis.",
  },
  {
    label: "Shares Outstanding",
    formula: "Shares Outstanding",
    meaning: "Common shares used as the per-share denominator.",
  },
  {
    label: "30 Year Treasury (DGS30)",
    formula: "Year-end 30-year Treasury yield",
    meaning:
      "The 30-year U.S. Treasury yield for that year, from Federal Reserve Economic Data (FRED).",
  },
  {
    label: "Owner Earnings / 30 Year Treasury per Share",
    formula: "(Owner Earnings ÷ Shares) ÷ 30-year Treasury yield",
    meaning:
      "Owner earnings per share compared with that year's 30-year Treasury yield, shown as dollars.",
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
    })),
  };
}

export { LOCKED_LABELS };
