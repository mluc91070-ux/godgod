import Link from "next/link";

import Hero from "@/components/Hero";
import { Disconnected } from "@/components/ui";
import { api, clock } from "@/lib/api";
import type { Live, Observation, Page, TokenInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  // The field draws the population, so the population is fetched with the
  // state. Both are allowed to fail on their own: a missing token list falls
  // back to the sphere rather than taking the page down.
  const [result, tokensResult, observationsResult] = await Promise.all([
    api<Live>("/api/live"),
    api<Page<TokenInfo>>("/api/tokens?limit=500"),
    api<Page<Observation>>("/api/observations?limit=120"),
  ]);
  const tokens = tokensResult.ok ? tokensResult.data.items : [];
  const observations = observationsResult.ok ? observationsResult.data.items : [];

  // A backend that is asleep or slow must not take the page down with it. The
  // hero and the identity are static; only the live numbers are missing, and
  // the page says exactly that instead of showing nothing.
  if (!result.ok) {
    return (
      <div className="mx-auto flex max-w-6xl flex-col items-center">
        <div className="flex w-full items-baseline justify-between">
          <h1 className="font-display text-[13px] tracking-[0.2em]">GODGOD</h1>
          <span className="text-[10px] uppercase tracking-widest text-muted">
            state unavailable
          </span>
        </div>

        <div className="my-10 w-full">
          <Hero
            state="IDLE"
            activity={0}
            novelty={null}
            confidence={null}
            tokens={tokens}
            observations={observations}
          />
        </div>

        <div className="w-full max-w-2xl space-y-6">
          <p className="text-center font-display text-[10px] uppercase tracking-[0.3em] text-grey">
            the autonomous meme researcher
          </p>
          <Disconnected error={result.error} what="the current state" />
        </div>
      </div>
    );
  }

  const live = result.data;

  return (
    <div className="mx-auto flex max-w-6xl flex-col items-center">
      <div className="flex w-full items-baseline justify-between">
        <h1 className="font-display text-[13px] tracking-[0.2em]">GODGOD</h1>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted">
          <span className={live.activity > 0 ? "text-amber" : "text-muted"}>
            {live.streaming ? "live" : "last cycle"}
          </span>
          <span>{clock(live.updated_at)}</span>
        </div>
      </div>

      <div className="my-10 w-full">
        <Hero
          state={live.state}
          activity={live.activity}
          novelty={live.novelty}
          confidence={live.confidence}
          tokens={tokens}
          observations={observations}
        />
      </div>

      <div className="w-full max-w-2xl space-y-8">
        <p className="text-center font-display text-[10px] uppercase tracking-[0.3em] text-grey">
          the autonomous meme researcher
        </p>

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
