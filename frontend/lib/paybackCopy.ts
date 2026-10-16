export type PaybackBlock = {
  price: number;
  oe_per_share_latest?: number | null;
  oe_per_share_5y_avg?: number | null;
  years_at_latest?: number | null;
  years_at_5y_avg?: number | null;
  /** How many annual years went into oe_per_share_5y_avg (#58). */
  oe_avg_years?: number | null;
  treasury_years?: number | null;
  pays_back: boolean;
};

function money(price: number): string {
  return `$${price.toFixed(2)}`;
}

function years(value: number): string {
  return value.toFixed(1);
}

/** Sentence for the ticker-page payback section. Null when there is nothing to say. */
export function paybackSentence(
  ticker: string,
  payback: PaybackBlock | null | undefined,
): string | null {
  if (!payback) return null;
  const price = money(payback.price);
  if (!payback.pays_back) {
    return `At ${price}, ${ticker} doesn't pay back on current earnings.`;
  }
  if (payback.years_at_latest == null) return null;
  let sentence = `At ${price} you get your money back in about ${years(payback.years_at_latest)} years from latest owner earnings`;
  if (payback.years_at_5y_avg != null) {
    const n = payback.oe_avg_years;
    const label = n != null && n !== 5 ? `${n}y avg` : "5y avg";
    sentence += ` (about ${years(payback.years_at_5y_avg)} years on the ${label})`;
  }
  if (payback.treasury_years != null) {
    sentence += `, vs ~${years(payback.treasury_years)} years at the 30-year Treasury`;
  }
  return `${sentence}.`;
}
