import type { Metadata } from "next";
import { indexLabel, parseSectorScope } from "@/lib/sectorTable";
import { PageShell, TextLink } from "../../components";
import { SectorTable } from "../../sector-table";

type Params = { slug: string };
type SearchParams = { index?: string | string[] };

function titleFromSlug(slug: string): string {
  return slug
    .split("-")
    .map((w) => (w === "and" ? "&" : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { slug } = await params;
  return {
    title: `${titleFromSlug(slug)} · S&P sector table - LongMuch`,
    description: "S&P 500 and S&P 1500 names in one GICS group, by owner-earnings yield, from the daily screen snapshot.",
  };
}

export default async function SectorPage({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: Promise<SearchParams>;
}) {
  const { slug } = await params;
  const query = await searchParams;
  const rawIndex = Array.isArray(query.index) ? query.index[0] ?? null : query.index ?? null;
  const initialScope = parseSectorScope(rawIndex) ?? "sp500";
  const screenHref = initialScope === "sp1500" ? "/screen?index=sp1500" : "/screen";

  return (
    <PageShell maxWidth="wide" textAlign="start">
      <p className="mb-6 text-sm text-zinc-500">
        <TextLink href="/">Back to LongMuch</TextLink>
        {" · "}
        <TextLink href={screenHref}>{indexLabel(initialScope)} screen</TextLink>
      </p>
      <h1 className="text-3xl sm:text-5xl font-bold tracking-tighter mb-4">Sector comparison</h1>
      <p className="text-zinc-400 mb-6 text-sm sm:text-base">
        Owner-earnings yield is the lower of latest-year owner earnings per share divided by the
        prior close, and the average of that yield over the newest annual years (up to five). NI
        margin is the lower of the latest year and that same window. Payback is the longer of price
        divided by latest owner earnings per share and price divided by the average. The small label
        says which one is shown. A non-positive latest owner earnings per share leaves payback blank.
        Debt/equity is total debt over total equity for those years. Grouped by GICS across S&P 500
        or S&P 1500.
      </p>
      <SectorTable kind="slug" slug={slug} initialScope={initialScope} />
    </PageShell>
  );
}
