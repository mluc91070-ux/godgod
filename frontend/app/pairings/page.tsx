import { PairingExample } from "@/components/examples";
import { Label, Nothing, Section } from "@/components/ui";
import { api, fmtInt, fmtUsd } from "@/lib/api";
import type { PairingSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "pairings",
  description:
    "What each measured pool is priced in. Memes quoted in tokenised shares are a different instrument from memes quoted in the gas token, and the split is the population of an open hypothesis.",
};

const EQUITY = "tokenised-equity";
const GAS = "gas";

const KIND_LABEL: Record<string, string> = {
  [EQUITY]: "a tokenised share",
  [GAS]: "the chain's gas token",
  other: "something else — a stablecoin, another meme",
  unknown: "the source described the pair and it was neither",
};

/**
 * The denominator.
 *
 * A price is a ratio and half of it is what the pool is quoted in. This system
 * measured both halves of that ratio for months and recorded only one, so a
 * meme priced in a tokenised share of a company and a meme priced in the gas
 * token arrived as the same kind of row. They are not: the first one's chart
 * is not separable from that company's without the pair data, and the depth on
 * the equity side is a constraint on the meme side.
 *
 * This page is a population, not a result. It shows that both arms of the
 * comparison exist and how large each one is, which is exactly what two of the
 * standing findings could not say — they were inconclusive because one side
 * was empty. The comparison itself is run by the research cycle, and it
 * publishes its own verdict including INCONCLUSIVE.
 */
export default async function PairingsPage() {
  const result = await api<PairingSummary>("/api/pairings");

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-4xl px-5 py-16">
        <Label>pairings</Label>
        <div className="mt-6">
          <Nothing
            what="the pairings"
            unreachable
            error={result.error}
            because=""
            needs={[
              "what every measured pool is priced in — the denominator of the ratio a price is",
              "a meme quoted in a tokenised share of a company is not the same instrument as one quoted in the gas token",
              "the split is the population of an open hypothesis, shown before that hypothesis has an answer",
            ]}
          >
            <PairingExample />
          </Nothing>
        </div>
      </div>
    );
  }

  const { counts, chains, equity_quoted: equity, marker, hypothesis_key } = result.data;
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const kinds = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const chainRows = Object.entries(chains)
    .map(([chain, split]) => ({
      chain,
      split,
      total: Object.values(split).reduce((sum, count) => sum + count, 0),
    }))
    .sort((a, b) => b.total - a.total);

  return (
    <main className="mx-auto max-w-4xl px-5 py-16">
      <Label>pairings</Label>
      <h1 className="mt-2 text-2xl text-bone">what each pool is priced in</h1>

      <p className="mt-5 max-w-2xl text-muted">
        A price is a ratio. This is the denominator, read from the deepest pool of every
        token under measurement — the same pool the price comes from, because the
        denominator has to belong to the numerator.
      </p>
      <p className="mt-3 max-w-2xl text-muted">
        A meme quoted in a tokenised share of a company is not the same instrument as a
        meme quoted in the chain&rsquo;s own gas token. Whether that changes how it behaves
        is a question, and a question needs the two groups told apart before it can be
        asked. Nothing on this page is an answer.
      </p>

      {total === 0 ? (
        <div className="mt-10">
          <Nothing
            what="recorded quote assets"
            because="the column that records what a pool is priced in is newer than most of the series. rows written before it existed report nothing and are absent here rather than counted as unknown — “not recorded” is not a kind of pool, and putting them in a bucket would make silence look like a measurement."
            needs={[
              "one collection run on a build that records the quote asset",
              "the market source reporting a quote token for the pair, which it does not always do",
              "nothing else — the split appears on the first run and grows from there",
            ]}
          >
            <PairingExample />
          </Nothing>
        </div>
      ) : (
        <>
          <Section title="the split" note={`${fmtInt(total)} tokens with a recorded quote`}>
            <ul className="divide-y divide-line">
              {kinds.map(([kind, count]) => (
                <li key={kind} className="flex flex-wrap items-baseline gap-x-4 py-2">
                  <span className={kind === EQUITY ? "text-amber" : "text-bone"}>{kind}</span>
                  <span className="text-[11px] text-muted">{KIND_LABEL[kind] ?? kind}</span>
                  <span className="ml-auto text-bone">{fmtInt(count)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[11px] text-muted">
              The classification reads the quote token&rsquo;s <em>name</em> for{" "}
              <code className="text-bone">{marker}</code>, not its symbol. A symbol is free
              text anyone can mint, and claiming a famous ticker costs nothing.
            </p>
          </Section>

          {chainRows.length > 1 ? (
            <Section title="per chain" note="every comparison here is held within one">
              <ul className="divide-y divide-line">
                {chainRows.map(({ chain, split, total: chainTotal }) => (
                  <li key={chain} className="py-3">
                    <div className="flex items-baseline gap-x-4">
                      <span className="text-bone">{chain}</span>
                      <span className="ml-auto text-[11px] text-muted">
                        {fmtInt(chainTotal)} measured
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-5 text-[11px] text-muted">
                      {Object.entries(split)
                        .sort((a, b) => b[1] - a[1])
                        .map(([kind, count]) => (
                          <span key={kind} className={kind === EQUITY ? "text-amber" : undefined}>
                            {kind} {fmtInt(count)}
                          </span>
                        ))}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[11px] text-muted">
                A chain with no equity wrappers on it reports an empty exposed arm. That is a
                true statement about that chain, not a gap in the measurement.
              </p>
            </Section>
          ) : null}

          <Section
            title="quoted in a tokenised share"
            note="deepest first — this is the exposed arm"
          >
            {equity.length === 0 ? (
              <Nothing
                what="equity-quoted pools"
                because="every pool measured so far is priced in the gas token or in something else. on a chain that issues no tokenised equities this is the correct and permanent answer, and an empty exposed arm is a true statement about that chain rather than a gap in the measurement."
                needs={[
                  "a chain that issues tokenised equities, and a marker matching how it names them",
                  "a pool quoted against one of those wrappers, above the frame's own liquidity floor",
                  "EQUITY_QUOTE_MARKER still matching — if the chain renames its wrappers the classifier goes quiet rather than guessing",
                ]}
              />
            ) : (
              <ul className="divide-y divide-line">
                {equity.map((row) => (
                  <li key={`${row.chain}:${row.address}`} className="py-3">
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                      <span className="text-bone">{row.symbol ?? row.address.slice(0, 10)}</span>
                      <span className="text-amber">/{row.quote_symbol ?? "?"}</span>
                      <span className="text-[10px] uppercase tracking-widest text-muted">
                        {row.chain}
                      </span>
                      {row.source ? (
                        <span className="text-[10px] uppercase tracking-widest text-muted">
                          found by {row.source}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-6 text-[11px] text-muted">
                      <span>mc {fmtUsd(row.market_cap_usd)}</span>
                      <span>liquidity {fmtUsd(row.liquidity_usd)}</span>
                      <span>volume {fmtUsd(row.volume_usd)}</span>
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-grey">{row.address}</div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="what is being asked" note={hypothesis_key}>
            <p className="text-muted">
              Whether a token quoted in a tokenised share holds its valuation better than one
              quoted in the gas token, six hours out, compared within the same chain and the
              same liquidity band.
            </p>
            <p className="mt-3 text-[11px] text-muted">
              Pools quoted in anything else, and pools the source did not describe, are in{" "}
              <em>neither</em> arm. Without that they would all land in the baseline, and the
              control group would quietly become &ldquo;gas-quoted pools, plus every pool we
              could not describe&rdquo;. Silence is not a comparison group.
            </p>
            <p className="mt-3 text-[11px] text-muted">
              The exposure is a standing property rather than an event, so a token&rsquo;s rows
              are perfectly correlated with each other. The critic checks independence and will
              say so. That is the honest form of this question, not a reason to dress it up as
              something it is not.
            </p>
          </Section>
        </>
      )}
    </main>
  );
}
