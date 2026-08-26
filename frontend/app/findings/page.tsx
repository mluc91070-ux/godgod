import Link from "next/link";

import { Disconnected, Empty, Label, Tag } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { Experiment, ExperimentResult, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

const ORDER = ["SUPPORTED", "REJECTED", "INCONCLUSIVE"];

const BLURB: Record<string, string> = {
  SUPPORTED: "the effect held and the critic passed.",
  REJECTED: "the falsification condition, written before the data was seen, was met.",
  INCONCLUSIVE: "the data cannot separate the hypothesis from the baseline.",
};

type Props = { searchParams: Promise<{ outcome?: string }> };

export default async function FindingsPage({ searchParams }: Props) {
  const { outcome } = await searchParams;
  const filter = outcome?.toUpperCase();

  const [results, experiments] = await Promise.all([
    api<Page<ExperimentResult>>(
      `/api/results?limit=200${filter ? `&outcome=${encodeURIComponent(filter)}` : ""}`,
    ),
    api<Page<Experiment>>("/api/experiments?limit=200"),
  ]);

  if (!results.ok) return <Disconnected error={results.error} what="results" />;

  const titles = new Map(
    experiments.ok ? experiments.data.items.map((item) => [item.id, item.title]) : [],
  );

  const counts = new Map<string, number>();
  for (const result of results.data.items) {
    counts.set(result.outcome, (counts.get(result.outcome) ?? 0) + 1);
  }

  const grouped = ORDER.map((name) => ({
    name,
    items: results.data.items.filter((item) => item.outcome === name),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>findings</Label>
        <span className="text-[10px] text-muted">{results.data.total} results recorded</span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        every result this system has produced, in the state it produced it. a rejection is not
        withdrawn for being disappointing and an inconclusive is not rounded up into a claim.
      </p>

      <div className="mt-6 flex flex-wrap gap-3 text-[10px] uppercase tracking-widest">
        <Link
          href="/findings"
          className={`border px-2 py-[2px] ${filter ? "border-line text-muted" : "border-bone text-bone"}`}
        >
          all
        </Link>
        {ORDER.map((name) => (
          <Link
            key={name}
            href={`/findings?outcome=${name.toLowerCase()}`}
            className={`border px-2 py-[2px] ${
              filter === name ? "border-bone text-bone" : "border-line text-muted"
            }`}
          >
            {name.toLowerCase()}
            {counts.has(name) ? ` ${counts.get(name)}` : ""}
          </Link>
        ))}
      </div>

      <div className="mt-8 space-y-10">
        {grouped.length === 0 ? (
          <Empty>no result has been recorded under that filter.</Empty>
        ) : (
          grouped.map((group) => (
            <section key={group.name}>
              <div className="flex flex-wrap items-baseline gap-3 border-b border-line pb-2">
                <Tag value={group.name} />
                <span className="text-[11px] text-muted">{BLURB[group.name]}</span>
              </div>

              <ul className="divide-y divide-line">
                {group.items.map((result) => (
                  <li key={result.id} className="py-4">
                    <Link
                      href={`/experiments/${result.experiment_id}`}
                      className="block hover:text-amber"
                    >
                      {titles.get(result.experiment_id) ?? "experiment"}
                    </Link>
                    <p className="mt-2 text-muted">{result.summary}</p>
                    <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
                      <span>p {fmt(result.p_value, 3)}</span>
                      <span>effect {fmt(result.effect_size)}</span>
                      <span>confidence {fmt(result.confidence)}</span>
                      <span className="flex items-center gap-2">
                        critic <Tag value={result.critic_verdict} />
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <p className="mt-8 text-[11px] text-muted">
        a hypothesis reaches supported only with a passing critic. everything else that survives
        review is inconclusive, which on the current data is most of it — six tokens is not enough
        independent history to settle a question.
      </p>
    </div>
  );
}
