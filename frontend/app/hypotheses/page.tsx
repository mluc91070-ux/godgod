import Link from "next/link";

import ResearchAge from "@/components/ResearchAge";
import { Disconnected, Empty, Label, Tag } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { Hypothesis, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

const STATUSES = ["PROPOSED", "TESTING", "SUPPORTED", "REJECTED", "INCONCLUSIVE"];

type Props = { searchParams: Promise<{ status?: string }> };

export default async function HypothesesPage({ searchParams }: Props) {
  const { status } = await searchParams;
  const filter = status?.toUpperCase();

  const result = await api<Page<Hypothesis>>(
    `/api/hypotheses?limit=100${filter ? `&status=${encodeURIComponent(filter)}` : ""}`,
  );

  if (!result.ok) return <Disconnected error={result.error} what="hypotheses" />;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>hypotheses</Label>
        <span className="text-[10px] text-muted">{result.data.total} recorded</span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        each question states what would prove it wrong before it is tested. open one to see the
        design, the memories consulted while writing it, and the experiments run against it.
      </p>

      <div className="mt-6 flex flex-wrap gap-3 text-[10px] uppercase tracking-widest">
        <Link
          href="/hypotheses"
          className={`border px-2 py-[2px] ${filter ? "border-line text-muted" : "border-bone text-bone"}`}
        >
          all
        </Link>
        {STATUSES.map((name) => (
          <Link
            key={name}
            href={`/hypotheses?status=${name.toLowerCase()}`}
            className={`border px-2 py-[2px] ${
              filter === name ? "border-bone text-bone" : "border-line text-muted"
            }`}
          >
            {name.toLowerCase()}
          </Link>
        ))}
      </div>

      <div className="mt-8">
        {result.data.items.length === 0 ? (
          filter ? (
            <Empty>no hypothesis has been recorded under that filter.</Empty>
          ) : (
            <ResearchAge what="question has been posed" />
          )
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {result.data.items.map((hypothesis) => (
              <li key={hypothesis.id}>
                <Link
                  href={`/hypotheses/${hypothesis.id}`}
                  className="block py-4 hover:bg-surface"
                >
                  <div className="flex flex-col gap-1 sm:grid sm:grid-cols-[5rem_1fr_8rem] sm:items-baseline sm:gap-4">
                    <span className="text-muted">
                      #{String(hypothesis.seq ?? 0).padStart(6, "0")}
                    </span>
                    <span>{hypothesis.question}</span>
                    <span className="flex justify-end">
                      <Tag value={hypothesis.status} />
                    </span>
                  </div>
                  <p className="mt-2 flex flex-col gap-0.5 text-[11px] text-muted sm:grid sm:grid-cols-[5rem_1fr] sm:gap-4">
                    <span>falsified if</span>
                    <span className="text-amber">{hypothesis.falsification_condition}</span>
                  </p>
                  <p className="mt-1 flex flex-col gap-0.5 text-[11px] text-muted sm:grid sm:grid-cols-[5rem_1fr] sm:gap-4">
                    <span>confidence</span>
                    <span>{fmt(hypothesis.confidence)}</span>
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
