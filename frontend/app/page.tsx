import Link from "next/link";

import AnomalyField from "@/components/AnomalyField";
import { Disconnected } from "@/components/ui";
import { api, clock } from "@/lib/api";
import type { Live } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  const result = await api<Live>("/api/live");

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-3xl">
        <Disconnected error={result.error} what="the current state" />
      </div>
    );
  }

  const live = result.data;

  return (
    <div className="mx-auto flex max-w-5xl flex-col items-center">
      <div className="flex w-full items-baseline justify-between">
        <h1 className="text-[11px] tracking-widest">GODGOD</h1>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted">
          <span className={live.activity > 0 ? "text-lime" : "text-muted"}>
            {live.streaming ? "live" : "last cycle"}
          </span>
          <span>{clock(live.updated_at)}</span>
        </div>
      </div>

      <div className="my-12">
        <AnomalyField
          state={live.state}
          activity={live.activity}
          novelty={live.novelty}
          confidence={live.confidence}
        />
      </div>

      <div className="w-full max-w-2xl space-y-8">
        <div className="text-center text-[10px] uppercase tracking-widest text-muted">
          state <span className="text-bone">{live.state}</span>
        </div>

        {live.current_observation ? (
          <p className="text-center">
            <span className="text-muted">observation #{live.current_observation.seq ?? "—"} — </span>
            {live.current_observation.summary}
          </p>
        ) : null}

        {live.current_hypothesis ? (
          <p className="text-center text-muted">
            <Link href="/hypotheses" className="hover:text-bone">
              hypothesis #{live.current_hypothesis.seq ?? "—"}
            </Link>{" "}
            — {live.current_hypothesis.question}{" "}
            <span className="text-bone">{live.current_hypothesis.status.toLowerCase()}</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}
