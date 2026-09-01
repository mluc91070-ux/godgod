import { Disconnected, Empty, Label, Section } from "@/components/ui";
import { api, fmtUsd } from "@/lib/api";
import type { Memory, Page, TokenInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "watchlist",
  description:
    "Tokens named by hand on Robinhood Chain, the claims made about why they ran, and the measurements next to them.",
};

/**
 * The named tokens, the claims about them, and what they actually measure.
 *
 * This page exists because the two things belong side by side and nowhere
 * else on the site would put them there honestly. Everything under "why it
 * ran" is somebody's claim, untested, and the page says so on every card. The
 * numbers beside it are this system's own readings.
 *
 * The reason these tokens are kept out of every experiment is the same reason
 * the page is interesting: the list was written after seeing which ones ran.
 * That makes it a set of survivors, and a rate computed over survivors is a
 * fact about whoever wrote the list. Watching is a different use from
 * comparing, and the two are kept apart rather than blurred.
 */
export default async function WatchlistPage() {
  const [notesResult, tokensResult] = await Promise.all([
    api<Page<Memory>>("/api/memory?type=token&limit=100"),
    api<Page<TokenInfo>>("/api/tokens?limit=200"),
  ]);

  if (!notesResult.ok) {
    return <Disconnected error={notesResult.error} what="the watchlist notes" />;
  }

  // Only the hand-written ones. Anything the system derives about a token also
  // lands under this type, and the two must not be shown as one thing.
  const notes = notesResult.data.items.filter((item) => item.source === "operator-note");

  const measured = new Map<string, TokenInfo>();
  if (tokensResult.ok) {
    for (const token of tokensResult.data.items) {
      measured.set(token.address.toLowerCase(), token);
    }
  }

  const meta = (note: Memory, key: string) => note.meta?.[key];
  const text = (note: Memory, key: string) => {
    const value = meta(note, key);
    return typeof value === "string" ? value : null;
  };
  const number = (note: Memory, key: string) => {
    const value = meta(note, key);
    return typeof value === "number" ? value : null;
  };

  return (
    <div className="mx-auto max-w-4xl space-y-10">
      <div>
        <Label>watchlist</Label>
        <p className="mt-4 max-w-2xl text-muted">
          Tokens named by hand, the claim made about why each one ran, and what this system
          measures beside it. Nothing here is a result.
        </p>
      </div>

      <Section title="what this page is not" note="read this before the cards">
        <ul className="space-y-1 text-muted">
          <li>
            — not a finding. no experiment has been run on any of it, and the claims were
            written by a person, not derived from a measurement.
          </li>
          <li>
            — not a sample. the list was written after seeing which tokens ran, so every entry
            is a survivor. that is why these rows are dropped from every dataset by name: a
            rate computed over survivors is a fact about whoever wrote the list.
          </li>
          <li>
            — not a recommendation, and not a price claim. the measurements are readings, not
            forecasts.
          </li>
          <li>
            — the market caps come in pairs on purpose. one is the figure supplied with the
            note, one is what the market source said. on one token they disagree by more than
            half, which is why they are never merged.
          </li>
        </ul>
      </Section>

      <Section title="the tokens" note="claim on the left, measurement on the right">
        {notes.length === 0 ? (
          <Empty>no notes are held.</Empty>
        ) : (
          <div className="space-y-8">
            {notes.map((note) => {
              const address = text(note, "address") ?? "";
              const live = measured.get(address.toLowerCase());
              const claimed = text(note, "claimed_market_cap");
              const atImport = number(note, "measured_market_cap_usd");
              return (
                <article key={note.id} className="border-l border-line pl-6">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
                    <span className="text-bone">{text(note, "symbol") ?? "—"}</span>
                    <span>{text(note, "chain") ?? "—"}</span>
                    <span className="break-all normal-case tracking-normal">{address}</span>
                  </div>

                  <p className="mt-3 whitespace-pre-line text-muted">{note.content}</p>

                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
                    <div className="flex gap-2">
                      <dt>claimed mcap</dt>
                      <dd className="text-grey">{claimed ?? "—"}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt>measured at filing</dt>
                      <dd className="text-bone">{fmtUsd(atImport)}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt>measured now</dt>
                      {/* Absent means this system has not measured it yet, which
                          is a different statement from a token worth nothing. */}
                      <dd className="text-bone">
                        {live ? fmtUsd(live.market_cap_usd) : "not measured yet"}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt>liquidity now</dt>
                      <dd className="text-bone">
                        {live ? fmtUsd(live.liquidity_usd) : "—"}
                      </dd>
                    </div>
                  </dl>

                  <p className="mt-2 text-[10px] uppercase tracking-widest text-muted">
                    untested claim · source {note.source} · excluded from every dataset
                  </p>
                </article>
              );
            })}
          </div>
        )}
      </Section>
    </div>
  );
}
