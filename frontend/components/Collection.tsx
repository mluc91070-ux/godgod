import { Label } from "@/components/ui";
import { fmtInt, fmtTime } from "@/lib/api";
import type { Status } from "@/lib/types";

/**
 * What the live collectors have gathered so far.
 *
 * Shown while the site still serves the demo dataset, because the collectors
 * run regardless and hiding that would make real work invisible. The progress
 * bar measures distance to the point where a detector can speak — not
 * completion of anything, and it says so.
 */
export default function Collection({ status }: { status: Status }) {
  const c = status.collection;
  const ratio = Math.min(1, c.deepest_history / Math.max(1, c.needed_to_observe));
  // Counted, never listed from configuration: a chain that is configured but
  // has had nothing measured on it yet must not appear here with a zero.
  const chains = Object.entries(c.tokens_by_chain ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <section className="border-t border-line pt-4">
      <div className="flex items-baseline justify-between gap-4">
        <Label>live collection</Label>
        <span className="text-[10px] text-muted">
          {c.observing_live ? "researching real measurements" : "measuring; still serving fixtures"}
        </span>
      </div>

      {/* Three numbers about the measurements. The social count used to sit
          here and was always zero — a column reporting the absence of a thing
          the site no longer talks about. /api/status still carries it. */}
      <div className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-3">
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">tokens measured</span>
          <span>{fmtInt(c.live_tokens)}</span>
        </div>
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">measurements</span>
          <span>{fmtInt(c.live_snapshots)}</span>
        </div>
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">observable tokens</span>
          <span>{fmtInt(c.tokens_ready_to_observe ?? 0)}</span>
        </div>
      </div>

      {/* The number that decides whether anything can be answered. A token is
          not a research subject until it has enough readings for a detector to
          speak, and most never used to get there — they left the promotion
          feed first. Shown against the total so the ratio is visible. */}
      <p className="mt-3 text-[11px] text-muted">
        <span className="text-bone">{fmtInt(c.tokens_ready_to_observe ?? 0)}</span> of{" "}
        {fmtInt(c.live_tokens)} tokens have the {c.needed_to_observe} measurements a detector needs
        before it may say anything. the rest were measured and then lost the feed — the
        largest by market cap are now kept under measurement on purpose, which is the only
        honest way to make that number move.
      </p>

      {/* Two networks, and the total would hide which one the tokens are on.
          The migrated frame reaches one of them, so the split is not cosmetic:
          it says which rows can carry a bonding curve at all. */}
      {chains.length > 1 ? (
        <div className="mt-3 grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {chains.map(([chain, count]) => (
            <div key={chain} className="flex justify-between border-b border-line py-1">
              <span className="text-muted">{chain}</span>
              <span>{fmtInt(count)}</span>
            </div>
          ))}
        </div>
      ) : null}

      {/* Two populations, and a total alone would hide which one grew. */}
      <div className="mt-3 grid gap-x-8 gap-y-2 sm:grid-cols-2">
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">promoted — someone paid to place it</span>
          <span>{fmtInt(c.tokens_promoted)}</span>
        </div>
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">migrated — a bonding curve that filled</span>
          <span>
            {c.migrations_available ? (
              fmtInt(c.tokens_migrated)
            ) : (
              <span className="text-grey" title="no launchpad configured">
                —
              </span>
            )}
          </span>
        </div>
      </div>

      {/* The fourth frame, and the only structural one. The others answer with
          whoever paid or whoever bought; this one answers with what a pool is
          denominated in — a fact about the pool rather than about the hour. */}
      {c.tokens_equity_quoted > 0 || (c.quote_kinds?.["tokenised-equity"] ?? 0) > 0 ? (
        <div className="mt-3 flex justify-between border-b border-line py-1 text-[11px]">
          <span className="text-muted">
            priced in a tokenised share, not in the gas token
          </span>
          <span className="text-amber">
            {fmtInt(c.quote_kinds?.["tokenised-equity"] ?? 0)}
          </span>
        </div>
      ) : null}

      {c.tokens_watchlist > 0 ? (
        <div className="mt-3 flex justify-between border-b border-line py-1 text-[11px]">
          <span className="text-muted">
            named by hand — a watchlist, not a sample
          </span>
          <span className="text-bone">{fmtInt(c.tokens_watchlist)}</span>
        </div>
      ) : null}

      <p className="mt-3 text-[11px] text-muted">
        {c.migrations_available
          ? "two sampling frames, kept apart. a result that holds in one and not the other is a result about the frame, not about the market."
          : "migrations are not being read, so the dash is 'not measured', not 'none found'."}
        {chains.length > 1
          ? " the migrated frame is read from a launchpad that covers solana only, so every token on another chain arrived through the promotion feed. no comparison is held across two chains."
          : null}
        {c.tokens_watchlist > 0
          ? " tokens named by hand are measured and shown like any other, and dropped from every dataset by name: the list was written after seeing which ones did well, so a rate computed over them is a fact about whoever wrote it."
          : null}
        {(c.quote_kinds?.["tokenised-equity"] ?? 0) > 0
          ? ` ${fmtInt(c.quote_kinds["tokenised-equity"])} of them are quoted in a tokenised share rather than in the chain's gas token, which makes them a different instrument and the population of an open question — see pairings.`
          : null}
        {c.tokens_unrecorded_frame > 0
          ? ` ${fmtInt(c.tokens_unrecorded_frame)} more were measured before the frame was recorded at all — they are not counted as either, because nobody wrote down which.`
          : null}
      </p>

      {!c.observing_live ? (
        <div className="mt-5">
          <div className="flex justify-between text-[10px] uppercase tracking-widest text-muted">
            <span>history on the most-measured token</span>
            <span>
              {c.deepest_history} of {c.needed_to_observe}
            </span>
          </div>
          <div className="mt-2 h-[3px] w-full bg-line">
            <div className="h-full bg-amber" style={{ width: `${ratio * 100}%` }} />
          </div>
          <p className="mt-3 text-[11px] text-muted">
            a detector needs {c.needed_to_observe} measurements of the same token before it can
            call anything unusual. one measurement is not a trend, so until then the research
            below runs on a synthetic dataset and says so on every row. this bar is distance to
            that threshold, not progress toward a result.
          </p>
        </div>
      ) : null}

      {/* The age of the dataset, which is what decides whether any question
          can be answered yet — not the age of the code. */}
      <p className="mt-4 text-[11px] text-muted">
        measuring since {fmtTime(c.measuring_since)}
        {c.running_since ? ` · running since ${fmtTime(c.running_since)}` : null}
      </p>

      <p className="mt-1 text-[11px] text-muted">
        last chain collection {fmtTime(c.last_chain_run_at)}
      </p>

      {/* Read from the running task, not from the setting that asked for it.
          A loop that died looks exactly like a market where nothing happened,
          so it has to be visible rather than inferred from a stale timestamp. */}
      <p className="mt-1 text-[11px] text-muted">
        {c.scheduler_running ? (
          <>
            measuring on its own clock, every{" "}
            {Math.round((c.scheduler_interval_seconds ?? 900) / 60)} minutes
          </>
        ) : (
          <span className="text-amber">
            the internal collection loop is not running — measurements depend on an
            external schedule, which is best-effort and skips
          </span>
        )}
      </p>
    </section>
  );
}
