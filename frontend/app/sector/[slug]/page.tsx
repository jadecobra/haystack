import type { Metadata } from "next";
import { PageShell, TextLink } from "../../components";
import { SectorTable } from "../../sector-table";

type Params = { slug: string };

function titleFromSlug(slug: string): string {
  return slug
    .split("-")
    .map((w) => (w === "and" ? "&" : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { slug } = await params;
  return {
    title: `${titleFromSlug(slug)} · S&P 500 sector table - LongMuch`,
    description: "S&P 500 names in one GICS group, by owner-earnings yield, from the daily screen snapshot.",
  };
}

export default async function SectorPage({ params }: { params: Promise<Params> }) {
  const { slug } = await params;
  return (
    <PageShell maxWidth="wide" textAlign="start">
      <p className="mb-6 text-sm text-zinc-500">
        <TextLink href="/">Back to LongMuch</TextLink>
        {" · "}
        <TextLink href="/screen">S&P 500 screen</TextLink>
      </p>
      <h1 className="text-3xl sm:text-5xl font-bold tracking-tighter mb-4">Sector comparison</h1>
      <p className="text-zinc-400 mb-6 text-sm sm:text-base">
        Trailing annual owner earnings per share divided by prior close, with payback years, NI/equity,
        and debt/equity from each company&apos;s latest 10-K year. S&P 500 only, grouped by GICS.
      </p>
      <SectorTable kind="slug" slug={slug} />
    </PageShell>
  );
}
