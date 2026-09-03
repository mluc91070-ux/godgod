import Link from "next/link";

import ResearchAge from "@/components/ResearchAge";
import { ExperimentExample } from "@/components/examples";
import { Label, Nothing, Tag } from "@/components/ui";
import { api, fmtInt } from "@/lib/api";
import type { Experiment, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ExperimentsPage() {
  const result = await api<Page<Experiment>>("/api/experiments?limit=50");

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-4xl">
        <Label>experiments</Label>
        <div className="mt-6">
          <Nothing
            what="experiments"
            unreachable
            error={result.error}
            because=""
            needs={[
              "each question run against its own dataset, hashed so the run can be repeated exactly",
              "every row that could not be built is counted under a named reason, and that list is usually larger than the dataset",
              "the critic's verdict can only be stricter than the deterministic one, never lighter",
            ]}
          >
            <ExperimentExample />
          </Nothing>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>experiments</Label>
        <span className="text-[10px] text-muted">{result.data.total} recorded</span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        one run of one question against its own dataset, on its own timescale — a withdrawal is
        asked about the next half day, a buy-side shift about the next hour. n counts the
        measurements the comparison actually held, not the tokens watched.
      </p>

      {result.data.items.length === 0 ? (
        <div className="mt-6">
          <ResearchAge what="experiment has been run">
            <ExperimentExample />
          </ResearchAge>
        </div>
      ) : null}

      <div className="mt-6 divide-y divide-line border-y border-line">
        {result.data.items.map((experiment) => (
          <Link
            key={experiment.id}
            href={`/experiments/${experiment.id}`}
            className="flex flex-col gap-1 py-4 hover:bg-surface sm:grid sm:grid-cols-[5rem_1fr_7rem_7rem] sm:items-center sm:gap-4"
          >
            <span className="text-muted">
              #{String(experiment.seq ?? 0).padStart(6, "0")}
            </span>
            <span>{experiment.title}</span>
            <span className="text-[11px] text-muted">n={fmtInt(experiment.sample_size)}</span>
            <span className="flex justify-end">
              <Tag value={experiment.status} />
            </span>
          </Link>
        ))}
      </div>

      <p className="mt-6 text-[11px] text-muted">
        every experiment page states its dataset, method, critic verdict and limitations. results
        that were rejected stay published.
      </p>
    </div>
  );
}
