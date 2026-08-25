import Link from "next/link";

import { Disconnected, Label, Tag } from "@/components/ui";
import { api, fmtInt } from "@/lib/api";
import type { Experiment, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ExperimentsPage() {
  const result = await api<Page<Experiment>>("/api/experiments?limit=50");

  if (!result.ok) return <Disconnected error={result.error} what="experiments" />;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>experiments</Label>
        <span className="text-[10px] text-muted">{result.data.total} recorded</span>
      </div>

      <div className="mt-6 divide-y divide-line border-y border-line">
        {result.data.items.map((experiment) => (
          <Link
            key={experiment.id}
            href={`/experiments/${experiment.id}`}
            className="grid grid-cols-[5rem_1fr_7rem_7rem] items-center gap-4 py-4 hover:bg-surface"
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
