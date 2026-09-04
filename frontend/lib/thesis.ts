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

/**
 * The event that made someone write the thesis down, with its numbers.
 *
 * This is the one place in this file that carries figures, so it carries their
 * provenance with them. They were read by hand, from the public pair index, at
 * the stated minute — they are not collector output, they are not graded, and
 * nothing re-reads them. A number that cannot be refreshed must say when it was
 * true, or it becomes a claim about now.
 *
 * `notClaimed` is not a disclaimer bolted on afterwards. A triggering event is
 * where a thesis is most likely to smuggle in a conclusion, so the sentence
 * naming what these figures do *not* establish is stored beside them and
 * renders with them.
 */
export type ThesisTrigger = {
  event: string;
  measuredAt: string;
  source: string;
  rows: { label: string; value: string; note: string }[];
  notClaimed: string;
};

export type Thesis = {
  key: string;
  title: string;
  posedBy: string;
  posedAt: string;
  /** The operator's own number for it, when it was posed publicly first. Not an
   *  internal id: nothing in the database is keyed by this. */
  posedAs?: string;
  claim: string;
  argument: string[];
  trigger?: ThesisTrigger;
  chain: ThesisLink[];
  falsification: string;
  confounds: { name: string; detail: string }[];
};

/** Newest first. A thesis is dated by when it was committed to, so the order is
 *  the order they were posed — not an order of confidence. */
export const THESES: Thesis[] = [
  {
    key: "tokenisation-retail-narrative",
    title:
      "Does putting tokenised equities next to memes produce longer-lived narratives, or only more speculation?",
    posedBy: "operator",
    posedAt: "2026-09-04",
    posedAs: "#0011",
    claim:
      "Robinhood Chain puts tokenised stocks in the same venue as memes, trading against each other, 24/7. The claim is that this chain — tokenisation, retail arriving, social coordination, liquidity, narrative — produces a different kind of meme than a purely speculative venue does. That it produces more speculation is not in question.",
    argument: [
      "Tokenised equities are not another asset listing. They put a share and a joke about that share in the same order book, at the same hours, priced in each other. The boundary between “financial asset” and “meme” is thinner here than anywhere this system has read before.",
      "GameStop showed what happens when retail attention becomes a social movement rather than a trade. The argument is that a venue combining retail finance, a financial identity people already have, and onchain social coordination can reproduce that — not the price action, the coordination.",
      "The mechanism claimed is a chain: tokenisation brings people in, arriving people coordinate, coordination brings liquidity, and liquidity is what a narrative needs in order to last longer than a session. On a venue optimised for short-horizon extraction, the same narrative gets sold into before it exists.",
      "The honest form of the question is not whether this creates speculation. It obviously does, and the numbers below are what speculation looks like. It is whether anything survives the speculation — whether a meme born beside a tokenised stock is still there in a month, or whether the equity quote is a costume on the same one-day lifecycle.",
    ],
    trigger: {
      event:
        "A meme took the ticker of a listed cinema chain, and inside a day the tokenised shares of that company had their deepest market priced in the meme rather than in a dollar.",
      measuredAt: "2026-09-04, read once by hand",
      source:
        "the public pair index, queried directly — not this system's collector, which has not run against these tokens",
      rows: [
        {
          label: "A Meme Coin · MEME · 0x385F…1e18",
          value: "$69.8M market cap · $162.4M traded in 24h · +315%",
          note: "all 30 of its pools were opened the same day it was measured",
        },
        {
          label: "AMC Entertainment • Robinhood Token · 0x05a3…222B",
          value: "$4.05M onchain · $234.7M traded in 24h · 129,660 buys / 118,629 sells",
          note: "the value of the tokenised shares that exist on this chain, at $2.73 each",
        },
        {
          label: "the deepest market for the tokenised equity",
          value: "AMC/MEME · $3.10M liquidity · $72.6M in 24h · opened the evening before",
          note: "the share is priced in the joke, not the other way round",
        },
      ],
      notClaimed:
        "These figures do not say a meme passed a listed company's market capitalisation. $4.05M is the tokenised float on one chain, not the company: this system reads pools, it does not read equity markets, and it has no source for a listed market cap — so that comparison is not made here. What is measured is the ratio between the meme and the tokenised float, and which of the two prices the other.",
    },
    chain: [
      {
        step: "tokenisation",
        detail:
          "that tokenised equities are actually there and actually quote other tokens — read from the quote side of the deepest pool, never from a symbol, which anyone can mint",
        fields: ["quote_kind", "quote_symbol"],
      },
      {
        step: "retail onboarding",
        detail:
          "new participants arriving rather than the same ones trading more — needs accounts, and this system reads pools",
        fields: ["holders"],
      },
      {
        step: "social coordination",
        detail:
          "attention converging on a token before its price does. No snapshot column carries this, and no onchain count is a substitute: buys and sells measure trading, which is the thing coordination is supposed to explain",
        fields: [],
      },
      {
        step: "liquidity",
        detail: "whether depth arrives and then stays, which is the part a narrative needs",
        fields: ["liquidity_usd", "volume_usd"],
      },
      {
        step: "new meme narratives",
        detail:
          "whether tokens born in this venue are still worth something later — the only link that answers the actual question",
        fields: ["market_cap_usd", "age_seconds", "liquidity_usd"],
      },
    ],
    falsification:
      "Take tokens first seen inside the equity-quote frame and tokens first seen inside the promotion feed, hold them to the same liquidity band and the same token-age band, and measure how much of the market cap and the depth is still there at a fixed horizon. If the survival gap is under the effect threshold, or points the other way, the chain above is wrong at its last link — and the last link is the claim. Onboarding numbers, volume records and a day like the one below would not rescue it, because none of them is survival.",
    confounds: [
      {
        name: "the venue is younger than the claim",
        detail:
          "Its mainnet opened on 2026-07-01 and this system has been measuring since 2026-08-26. “Longer-lived” is a statement about weeks. A horizon longer than the history cannot be observed, and quietly shortening it answers a different question under the original wording.",
      },
      {
        name: "the meme borrows the company's ticker",
        detail:
          "The token that set this off is called AMC, and so is the tokenised share. A pool cannot tell attention paid to the stock apart from attention paid to the joke about the stock, so a ticker collision would look exactly like the social coordination this thesis needs.",
      },
      {
        name: "onboarding is invisible from a pool",
        detail:
          "New people, existing people trading more, and one person with forty wallets produce the same rows. Nothing in this deployment distinguishes them, so the second link cannot be measured here — it is published as untestable rather than proxied by transaction counts.",
      },
      {
        name: "the trigger is hours old",
        detail:
          "Every figure under “what set it off” was read on the day it happened, at the top of the move. A day is the unit this thesis is arguing against, so it is evidence that something occurred and no evidence at all for the thing being claimed.",
      },
      {
        name: "the token set is a business decision",
        detail:
          "Which equities get tokenised is chosen by one company. The population is therefore not a sample of anything, and a result about it is partly a result about that listing policy — which is not what the thesis says it is measuring.",
      },
    ],
  },
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
