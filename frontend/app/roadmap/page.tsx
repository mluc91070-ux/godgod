import { Disconnected, Label, Section } from "@/components/ui";
import { fmtInt, fmtTime } from "@/lib/api";
import { getStatus } from "@/lib/status";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Roadmap",
  description:
    "What runs, what is in beta, what is waiting on measurement rather than on code, and what will never be built.",
};

/**
 * A roadmap that reads the system instead of describing it from memory.
 *
 * The counts, the horizons, the start date and the X stage all come from
 * `/api/status`. That is not decoration: the docs page spent two releases
 * claiming "the X and Solana providers, scheduled last" while Solana had been
 * collecting for days, and a roadmap is the single page most likely to rot the
 * same way. Anything here that cannot be derived is a decision rather than a
 * status, and those do not go stale.
 */
export default async function RoadmapPage() {
  const result = await getStatus();
  if (!result.ok) return <Disconnected error={result.error} what="the roadmap" />;

  const { collection, research, counts, mode } = result.data;
  const horizons = research.horizons_hours ?? [];
  const longest = horizons.length ? horizons[horizons.length - 1] : null;
  const days = collection.measuring_since
    ? Math.floor((Date.now() - Date.parse(collection.measuring_since)) / 86_400_000)
    : null;

  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <div>
        <Label>roadmap</Label>
        <h1 className="mt-3">what is built, what is next, what never will be</h1>
        <p className="mt-4 text-muted">
          Nothing on this page is a promise with a date attached. Three of the four sections
          describe the system as it is right now and are read from it; the fourth is a set of
          decisions, which is the only kind of future statement worth publishing.
        </p>
      </div>

      <Section title="running" note="read from /api/status">
        <ul className="space-y-2 text-muted">
          <li>
            — measuring since {fmtTime(collection.measuring_since)}
            {days !== null ? ` — ${days} days` : null}: {fmtInt(collection.live_tokens)} tokens,{" "}
            {fmtInt(collection.live_snapshots)} measurements, on the application&apos;s own clock
            every {Math.round((collection.scheduler_interval_seconds ?? 900) / 60)} minutes
          </li>
          <li>
            — two sampling frames kept apart: {fmtInt(collection.tokens_promoted)} found by the
            promotion feed, {fmtInt(collection.tokens_migrated)} by a completed bonding curve
          </li>
          {Object.keys(collection.tokens_by_chain ?? {}).length > 1 ? (
            <li>
              —{" "}
              {Object.entries(collection.tokens_by_chain)
                .sort((a, b) => (a[0] === "solana" ? -1 : b[0] === "solana" ? 1 : b[1] - a[1]))
                .map(([chain, count]) => `${fmtInt(count)} on ${chain}`)
                .join(", ")}
              , and no comparison held across the two — the migrated frame and the holder
              share are readable on solana alone, so elsewhere they are null rather than
              estimated
            </li>
          ) : null}
          <li>
            — a deterministic observation pipeline: {result.data.pipeline.detectors.length}{" "}
            detectors, {fmtInt(counts.observations)} observations, {fmtInt(counts.anomalies)}{" "}
            anomalies, no model anywhere in it
          </li>
          <li>
            — {research.hypothesis_templates} questions, each with its own window, horizon
            {horizons.length ? ` (${horizons.map((hour) => `${hour}h`).join(", ")})` : null} and
            its own comparison
          </li>
          <li>
            — a critic with {research.critic_checks.length} design checks, and the gate that
            stops an unearned finding becoming a claim
          </li>
          <li>— a public page for every question and every result, rejections included</li>
        </ul>
      </Section>

      <Section title="in beta">
        <ul className="space-y-2 text-muted">
          <li>
            — <span className="text-magenta">critic agent</span>: a model reads what the
            deterministic checks returned and may make the verdict harsher. It can never make it
            lighter, and an objection citing a number that is not in the result is discarded.
          </li>
          <li>
            — <span className="text-magenta">observer agent</span>: a model puts an anomaly a
            detector already found into a sentence. It cannot create, suppress or rescore one.
          </li>
          <li>
            — <span className="text-magenta">X</span>: stage{" "}
            <span className="text-bone">{mode.x_stage}</span>. The client is built and not
            connected — no credentials are set, so nothing is read and nothing is published.
            This page will say <span className="text-bone">live</span> when a post can actually
            go out, because that word is derived from whether it can.
          </li>
        </ul>
      </Section>

      <Section title="waiting on measurement, not on code">
        <p className="text-muted">
          These are not unfinished. They are questions that have been asked correctly and cannot
          be answered yet, which is a different thing and is worth being able to tell apart.
        </p>
        <ul className="mt-4 space-y-2 text-muted">
          <li>
            — every result so far is INCONCLUSIVE because the groups are too small. Thirty
            measurements a side is the floor for believing a difference, and that arrives by
            waiting, not by tuning a threshold.
          </li>
          {longest !== null ? (
            <li>
              — the {longest}h questions fill last: a token has to be watched for a whole window
              and then a whole horizon before it can answer one.
            </li>
          ) : null}
          <li>
            — the two questions that need holder counts have no rows at all. A public node
            cannot count holders, and estimating one would be inventing a measurement.
          </li>
        </ul>
      </Section>

      <Section title="decided against">
        <ul className="space-y-2 text-muted">
          <li>
            — <span className="text-bone">trading, signing, holding.</span> No private key
            exists in this system and no code path constructs a transaction. This is not a
            feature waiting for its turn.
          </li>
          <li>
            — <span className="text-bone">hypotheses written by a model.</span> A question comes
            from a template so that nothing reads the data before deciding what to claim about
            it. A falsification rule invented after the result is not a falsification rule.
          </li>
          <li>
            — <span className="text-bone">a model computing the statistics.</span> They have one
            right answer. A model there would trade a guarantee for a sentence.
          </li>
          <li>
            — <span className="text-bone">price predictions, targets, advice.</span> Nothing
            here has ever tested a claim of that shape, so the system is not allowed to make
            one — the check is mechanical, not a matter of tone.
          </li>
        </ul>
      </Section>
    </div>
  );
}
