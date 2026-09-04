import Link from "next/link";

import Hero from "@/components/Hero";
import { Disconnected } from "@/components/ui";
import { api, clock, fmtInt } from "@/lib/api";
import { THESES } from "@/lib/thesis";
import type { Live, Observation, Page, TokenInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  // The field draws the population, so the population is fetched with the
  // state. Both are allowed to fail on their own: a missing token list falls
  // back to the state sphere rather than taking the page down.
  //
  // Two pages, because the API caps a page at 200 and the field draws more
  // than that. Asking for 500 in one call is a 422, and a 422 here is silent:
  // the list comes back empty, the fallback renders, and the page looks fine
  // while showing something else. It shipped that way once.
  const [result, firstPage, secondPage, observationsResult] = await Promise.all([
    api<Live>("/api/live"),
    api<Page<TokenInfo>>("/api/tokens?limit=200"),
    api<Page<TokenInfo>>("/api/tokens?limit=200&offset=200"),
    api<Page<Observation>>("/api/observations?limit=120"),
  ]);
  const tokens = [
    ...(firstPage.ok ? firstPage.data.items : []),
    ...(secondPage.ok ? secondPage.data.items : []),
  ];
  const observations = observationsResult.ok ? observationsResult.data.items : [];

  // The networks under measurement, counted off the tokens already fetched —
  // no extra request, and it describes exactly what the field above it draws.
  // Counted, never listed from configuration: a chain that is configured but
  // has had nothing measured on it does not belong in a sentence that says
  // "measuring". Solana leads because it is the only one whose holder share
  // can be read and whose bonding curves are reported, not because it is
  // bigger.
  const chains = [...tokens.reduce((tally, token) => {
    tally.set(token.chain, (tally.get(token.chain) ?? 0) + 1);
    return tally;
  }, new Map<string, number>())].sort((a, b) =>
    a[0] === "solana" ? -1 : b[0] === "solana" ? 1 : b[1] - a[1],
  );

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
          {/* The thesis does not depend on the live state, so it stays
              reachable when the API is asleep. A visitor who just watched the
              field is asking what the system thinks is going on, and that
              question has an answer whether or not the backend is awake. */}
          <div className="text-center">
            <Link
              href="/thesis"
              className="inline-block border border-line px-5 py-2 font-display text-[10px] uppercase tracking-[0.25em] text-muted transition-colors hover:border-bone hover:text-bone"
            >
              read the theses
            </Link>
          </div>

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

        {/* One link under the field, because there is one thing a visitor who
            just watched the sphere is actually asking: what does it think is
            going on. A thesis is the only object here that answers that in a
            sentence — and the page it opens is careful to say it is an
            argument rather than a result. */}
        <div className="text-center">
          <Link
            href="/thesis"
            className="inline-block border border-line px-5 py-2 font-display text-[10px] uppercase tracking-[0.25em] text-muted transition-colors hover:border-bone hover:text-bone"
          >
            read the theses
          </Link>
          <p className="mt-2 text-[10px] text-grey">
            {THESES.length} arguments posed before the data existed to settle them
          </p>
        </div>

        {chains.length > 1 ? (
          <div className="space-y-2 text-center">
            <p className="font-display text-[11px] uppercase tracking-[0.3em] text-bone">
              {chains.map(([chain]) => chain).join(" · ")}
            </p>
            <p className="text-[11px] text-muted">
              {chains.map(([chain, count]) => `${fmtInt(count)} on ${chain}`).join(", ")} —
              measured by the same promotion feed into identical rows, and never compared
              across the two. bonding curves and holder shares are read on solana only, so
              a robinhood row carries neither rather than carrying a guess.
            </p>
          </div>
        ) : null}

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
