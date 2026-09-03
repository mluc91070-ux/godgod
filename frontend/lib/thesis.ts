/**
 * Posed theses. The argument lives here; the grading does not.
 *
 * The first version of this put the whole thing behind an API call, and it was
 * wrong for a reason worth writing down: an argument is not a measurement. A
 * paragraph somebody wrote does not become truer or falser because a backend
 * answered, so putting it behind one only means it disappears when the backend
 * is asleep, unreachable, or — as happened — running a build that does not have
 * the endpoint yet. The page went blank and said "no data", which was a lie
 * about the argument and told the reader nothing about the deploy.
 *
 * So the split follows what the thing actually is:
 *
 * - **the argument is static** and ships with the page. It makes no claim about
 *   any number, so nothing here can be stale or fabricated.
 * - **the grading is a measurement** and only ever comes from the database, via
 *   `/api/field-coverage`. When that does not answer, each link reads "not
 *   graded" — never "not measured", which is a different statement this file is
 *   in no position to make.
 *
 * `fields` is the join between the two. Each link names the snapshot columns
 * its step would need, and the API says how many live measurements carry them.
 * That is what stops a thesis from grading itself: this file may claim a
 * mechanism, it may not claim the mechanism was measured.
 */

export type ThesisLink = {
  step: string;
  detail: string;
  /** Snapshot columns this step needs. Counted by the API, never here. */
  fields: string[];
};

export type Thesis = {
  key: string;
  title: string;
  posedBy: string;
  posedAt: string;
  claim: string;
  argument: string[];
  chain: ThesisLink[];
  falsification: string;
  confounds: { name: string; detail: string }[];
};

export const THESES: Thesis[] = [
  {
    key: "chain-structure-runner-duration",
    title:
      "Do runners last longer on the newer chain because the people holding them behave differently?",
    posedBy: "operator",
    posedAt: "2026-09-03",
    claim:
      "Robinhood Chain may produce more long-duration runners than Solana, because its participants are different rather than because its tokens are.",
    argument: [
      "On Solana, aggressive short-horizon trading — copy-trading, farming, bots reacting to each other — can extract profit out of a move as fast as the move happens. A token that starts running becomes something to sell into rather than something to hold.",
      "That has a structural consequence rather than a moral one: repeated selling into momentum fragments the liquidity that price discovery needs. Without market-making depth behind it, a token that might have run becomes a venue for bots before its narrative has time to exist.",
      "Robinhood Chain appears to have a different participant profile — fewer ultra-short-term traders, potentially longer holding periods, and a structure more reachable by larger wallets. If that difference is real, it would explain a longer lifecycle for comparable launches.",
      "The explanation is not assumed to be correct. It is the thing being tested, and the chain below is where it can fail.",
    ],
    chain: [
      {
        step: "holder behaviour",
        detail:
          "who is holding, and for how long — the share of wallets that are ultra-short-horizon",
        fields: ["holders", "holder_concentration_top10"],
      },
      {
        step: "selling pressure",
        detail: "how much of the flow is sell-side while the token is moving",
        fields: ["buys", "sells"],
      },
      {
        step: "liquidity",
        detail: "whether the pool keeps its depth through the move",
        fields: ["liquidity_usd"],
      },
      {
        step: "holding duration",
        detail:
          "how long a given wallet stays in — needs per-wallet history, not a pool total",
        fields: ["holders"],
      },
      {
        step: "runner survival",
        detail: "whether the valuation and the market are still there later",
        fields: ["market_cap_usd", "liquidity_usd"],
      },
    ],
    falsification:
      "If sell-side share, depth retention and survival are measured on both chains inside the same sampling frame, the same liquidity band and the same token-age band, and the gap is under the effect threshold or points the other way, the structural explanation is wrong — whatever the participant profile turns out to be.",
    confounds: [
      {
        name: "the two chains are not sampled the same way",
        detail:
          "The launchpad frame reads a Solana launchpad; the equity-quote frame only returns tokens on the newer chain. Only the promotion feed runs identically on both, so any chain contrast has to be held inside that one frame or it measures the sampling rule instead of the chain.",
      },
      {
        name: "the newer chain cannot have old tokens",
        detail:
          "Its mainnet opened on 2026-07-01, so no token on it can be older than that, while Solana tokens can be years old. A survival comparison that is not stratified by token age would be measuring how long the chain has existed and reporting it as how long its tokens last.",
      },
      {
        name: "the series is shorter than the claim",
        detail:
          "“Long-duration” is a claim about weeks. This system has been measuring since 2026-08-26. A horizon longer than the history cannot be observed at all, and a shorter horizon standing in for it would be answering a different question under the original wording.",
      },
      {
        name: "survivorship in what is stored",
        detail:
          "A token that left the promotion feed before the retention floor stopped being measured. The tokens with the longest series are, by construction, partly the ones that lasted.",
      },
    ],
  },
];

export type LinkGrade = "measured" | "partly-measured" | "not-measured-here" | "not-graded";

/**
 * Grade one link against the coverage the API reported.
 *
 * `null` coverage means the API did not answer, and every link reads
 * `not-graded`. That is deliberately not `not-measured-here`: one says nobody
 * asked the database, the other says the database was asked and had nothing.
 * Collapsing them would let a deploy problem masquerade as a finding about the
 * data.
 */
export function gradeLink(
  link: ThesisLink,
  coverage: Record<string, number> | null,
): { grade: LinkGrade; counts: Record<string, number> | null; unknown: string[] } {
  if (coverage === null) {
    return { grade: "not-graded", counts: null, unknown: [] };
  }
  const unknown = link.fields.filter((name) => !(name in coverage));
  const known = link.fields.filter((name) => name in coverage);
  const counts = Object.fromEntries(known.map((name) => [name, coverage[name]]));
  const present = known.filter((name) => coverage[name] > 0);

  if (known.length === 0) return { grade: "not-measured-here", counts, unknown };
  if (present.length === known.length) return { grade: "measured", counts, unknown };
  return {
    grade: present.length > 0 ? "partly-measured" : "not-measured-here",
    counts,
    unknown,
  };
}
