import Link from "next/link";

import { Card } from "../components";
import { LOCKED_LABELS } from "@/lib/locked-labels";
import { resolveDocsModel } from "@/lib/metrics-catalog";

export const metadata = {
  title: "How metrics are calculated - LongMuch",
  description: "How LongMuch metrics are calculated and what they mean.",
};

export default function DocsPage() {
  const model = resolveDocsModel(LOCKED_LABELS);

  return (
    <main className="min-h-dvh bg-zinc-950 text-white overflow-x-hidden">
      <div className="w-full max-w-3xl mx-auto px-4 sm:px-6 py-10 sm:py-16 text-left">
        <p className="mb-6 text-sm text-zinc-500">
          <Link
            href="/"
            className="underline underline-offset-4 hover:text-zinc-300"
          >
            Back to LongMuch
          </Link>
        </p>

        <h1 className="text-3xl sm:text-5xl font-bold tracking-tighter mb-4">
          {model.title}
        </h1>
        <p className="text-zinc-400 mb-10 sm:mb-12 text-base sm:text-lg">
          What each row on the Analyze table means.
        </p>

        <section className="space-y-4 mb-12 sm:mb-16">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
            Primer
          </h2>
          {model.primer.map((block) => (
            <Card
              key={block.id}
              className="border-zinc-800 bg-zinc-900/60 text-left shadow-none hover:shadow-none"
            >
              <h3
                id={block.id}
                className="text-lg font-semibold text-zinc-100 mb-2 scroll-mt-8"
              >
                {block.heading}
              </h3>
              <ul className="list-disc pl-5 space-y-2 text-zinc-400 text-sm sm:text-base leading-relaxed">
                {block.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Card>
          ))}
        </section>

        <section className="space-y-4">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
            Metrics
          </h2>
          {model.entries.map((entry) => (
            <Card
              key={entry.label}
              className="border-zinc-800 bg-zinc-900/60 text-left shadow-none hover:shadow-none"
            >
              <h3
                id={entry.anchor}
                className="text-base sm:text-lg font-semibold text-zinc-100 mb-3 scroll-mt-8"
              >
                {entry.label}
              </h3>
              <dl className="space-y-2 text-sm sm:text-base">
                <div>
                  <dt className="text-zinc-500">Formula</dt>
                  <dd className="text-zinc-200 font-mono text-sm mt-0.5">
                    {entry.formula}
                  </dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Meaning</dt>
                  <dd className="text-zinc-300 mt-0.5">{entry.meaning}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </section>

        <p className="mt-12 text-zinc-500 text-sm">
          <Link
            href="/"
            className="underline underline-offset-4 hover:text-zinc-300"
          >
            Back to LongMuch
          </Link>
        </p>
      </div>
    </main>
  );
}
