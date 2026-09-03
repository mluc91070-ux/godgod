import { ExampleField, ExampleOf } from "@/components/ui";

/**
 * One worked example per kind of object on this site.
 *
 * They exist so that an empty page still says what it is for. A reader who
 * arrives at "findings" before any experiment has finished should be able to
 * see what a finding *is* — that it carries a verdict, an effect size in
 * percentage points, a group count and the rule that would have killed it —
 * rather than a grey box saying nothing yet.
 *
 * Everything here is invented, and three things make that unmistakable rather
 * than a matter of the reader noticing: the wrapper stamps every one of them,
 * the borders are dashed where real rows are solid, and every identifier is a
 * DEMO placeholder. That last rule is the same one the fixtures follow, and it
 * is the important one — an example must never be able to name a real token or
 * attach a number to one.
 *
 * The numbers are chosen to teach the honest case. The example finding is
 * INCONCLUSIVE with an underpowered group, because that is what most real
 * results here are and an example showing a triumphant confirmation would
 * misrepresent the system more than an empty page ever did.
 */

export function FindingExample() {
  return (
    <ExampleOf what="a finding">
      <ExampleField k="verdict" v="INCONCLUSIVE" />
      <ExampleField
        k="question"
        v="Does a burst of volume mean the pool is still there two hours later?"
      />
      <ExampleField k="exposed group" v="14 measurements" />
      <ExampleField k="control group" v="212 measurements" />
      <ExampleField k="difference" v="+3.1 points, expected +8 or more" />
      <ExampleField k="why inconclusive" v="the exposed group is under the minimum of 30" />
      <ExampleField k="dataset" v="token-measurements-v2 · 9f2c…41ab" />
      <p className="mt-3 text-grey">
        Inconclusive is a result and it is published like any other. Most findings here look
        like this one: a real comparison that did not have enough of one arm to answer. The
        decision order is deliberate — too small to judge outranks falsified — so a thin group
        can never be reported as a rejection.
      </p>
    </ExampleOf>
  );
}

export function PatternExample() {
  return (
    <ExampleOf what="a pattern">
      <ExampleField k="name" v="volume-burst-pool-2h" />
      <ExampleField k="times tested" v="6" />
      <ExampleField k="times supported" v="4" />
      <ExampleField k="confidence" v="0.41" />
      <ExampleField k="status" v="held, weakly" />
      <p className="mt-3 text-grey">
        A pattern is not a finding. It is the running record of one question asked repeatedly:
        how often the same template survived its own falsification rule across separate
        datasets. One supported result does not make a pattern, and a pattern that stops
        holding keeps its history rather than being deleted.
      </p>
    </ExampleOf>
  );
}

export function HypothesisExample() {
  return (
    <ExampleOf what="a hypothesis">
      <ExampleField
        k="question"
        v="Does a burst of volume mean the pool is still there two hours later?"
      />
      <ExampleField k="population" v="tokens with reported liquidity and hourly volume" />
      <ExampleField k="exposure" v="last hour's volume ≥ 3× the median of the previous three" />
      <ExampleField k="outcome" v="liquidity still at 80% of its level, read 2h later" />
      <ExampleField k="baseline" v="same chain and liquidity band, no burst" />
      <ExampleField
        k="falsified if"
        v="the gap is under 8 points, points the other way, or reverses between bands"
      />
      <ExampleField k="status" v="OPEN" />
      <p className="mt-3 text-grey">
        The last two lines are the ones that matter. A hypothesis is written from a template
        before anything looks at the data it will be tested on, and the rule that would kill it
        is fixed at the same moment — a falsification condition invented after the result is not
        a falsification condition.
      </p>
    </ExampleOf>
  );
}

export function ExperimentExample() {
  return (
    <ExampleOf what="an experiment">
      <ExampleField k="hypothesis" v="#12 — volume-burst-pool-2h" />
      <ExampleField k="unit of analysis" v="token-measurement" />
      <ExampleField k="rows" v="226 built · 1,904 excluded" />
      <ExampleField k="excluded, by reason" v="no_reading_at_horizon 1,502 · window_too_sparse 402" />
      <ExampleField k="dataset hash" v="9f2c…41ab" />
      <ExampleField k="critic" v="NEEDS_MORE_DATA — sample_size, independence" />
      <p className="mt-3 text-grey">
        Every row that could not be built is counted under a named reason. Silent filtering is
        what makes &ldquo;found nothing&rdquo; indistinguishable from &ldquo;looked at
        nothing&rdquo;, and the exclusion list is usually larger than the dataset.
      </p>
    </ExampleOf>
  );
}

export function ObservationExample() {
  return (
    <ExampleOf what="an observation">
      <ExampleField k="token" v="DEMOTOKENxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" />
      <ExampleField k="detector" v="volume-acceleration-v1" />
      <ExampleField k="measured" v="volume 4.2× its window median" />
      <ExampleField k="baseline" v="median of the preceding 3h, 11 readings" />
      <ExampleField k="thresholds used" v="volume_ratio 3.0 · saturation 12.0" />
      <ExampleField k="novelty" v="0.62" />
      <p className="mt-3 text-grey">
        An anomaly records the thresholds it fired on, so it stays interpretable after those
        thresholds change. Nothing here involves a model: the pipeline is deterministic, and the
        expensive layer only ever sees what these cheap functions already flagged.
      </p>
    </ExampleOf>
  );
}

export function MemoryExample() {
  return (
    <ExampleOf what="a memory">
      <ExampleField k="type" v="PATTERN" />
      <ExampleField k="summary" v="volume bursts did not predict depth on the demo cohort" />
      <ExampleField k="source" v="experiment #4" />
      <ExampleField k="confidence" v="0.35" />
      <ExampleField k="embedding" v="local-hashing-v1 · 1536 dims" />
      <p className="mt-3 text-grey">
        Memory is searched before a hypothesis is generated, so the system can notice it has
        asked something before. The embedder is a lexical hash rather than a language model, and
        the site says <span className="text-muted">semantic: false</span> because of it.
      </p>
    </ExampleOf>
  );
}

export function TokenExample() {
  return (
    <ExampleOf what="a measured token">
      <ExampleField k="address" v="DEMOTOKENxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" />
      <ExampleField k="chain" v="solana" />
      <ExampleField k="found by" v="promotion-feed" />
      <ExampleField k="liquidity" v="$84,200" />
      <ExampleField k="volume 24h" v="$310,000" />
      <ExampleField k="holders" v="NULL — no indexer, never estimated" />
      <ExampleField k="quote" v="WSOL · gas" />
      <p className="mt-3 text-grey">
        The holder line is the honest one. A public node cannot count holders, so the field
        stays NULL and the detectors that need it return no verdict rather than a wrong one.
      </p>
    </ExampleOf>
  );
}

export function EventExample() {
  return (
    <ExampleOf what="a terminal event">
      <div className="font-mono text-[10px] leading-relaxed text-grey">
        <div>12:00:04 OBSERVATION chain collector: 32 measurements of 57 candidates</div>
        <div>12:00:11 OBSERVATION anomaly: volume 4.2× median on DEMOTOKEN…</div>
        <div>12:00:19 ERROR launchpad: rate-limited, cursor not advanced</div>
        <div>12:15:00 OBSERVATION attention: 15 ranked entries stored, 1 tied to a token</div>
      </div>
      <p className="mt-3 text-grey">
        The stream is a cursor over committed events, never a second source of truth: nothing is
        emitted that was not written first. Silence is a valid state and no filler frame is ever
        synthesised to make the terminal look busy.
      </p>
    </ExampleOf>
  );
}

export function NarrativeExample() {
  return (
    <ExampleOf what="a change of mind">
      <ExampleField k="was" v="withdrawal of liquidity predicts collapse" />
      <ExampleField k="now" v="it does not — 8.4 points, wrong direction" />
      <ExampleField k="changed by" v="experiment #17" />
      <p className="mt-3 text-grey">
        This page holds the times a result overturned something the system had already written
        down. It is empty because that has not happened yet, which is the expected state on a
        few weeks of measurement — not a page that failed to load.
      </p>
    </ExampleOf>
  );
}

export function AgentExample() {
  return (
    <ExampleOf what="an agent">
      <ExampleField k="name" v="critic" />
      <ExampleField k="stage" v="model" />
      <ExampleField k="implemented" v="true — a model is actually called" />
      <ExampleField k="question" v="is this experiment's design sound?" />
      <ExampleField k="verdict power" v="can only make the deterministic verdict stricter" />
      <p className="mt-3 text-grey">
        Two of the agents on this roster are <span className="text-muted">deterministic</span>{" "}
        and report <span className="text-muted">implemented: false</span> — that is a finished
        state, not a backlog item. A hypothesis comes from a template so nothing reads the data
        before choosing what to claim about it, and the statistics have one right answer. An
        engine doing the same job is not the same claim as a model doing it.
      </p>
    </ExampleOf>
  );
}

export function RoadmapExample() {
  return (
    <ExampleOf what="a roadmap entry">
      <ExampleField k="built" v="observation pipeline · hypothesis templates · critic checks" />
      <ExampleField k="waiting on data" v="patterns — needs the same question asked twice" />
      <ExampleField
        k="waiting on an indexer"
        v="holder counts, and the three detectors that need them"
      />
      <ExampleField k="never" v="wallet execution · signing · transaction construction" />
      <p className="mt-3 text-grey">
        The last row is the honest one and it does not move. There is no private key, no seed
        phrase and no swap path anywhere in this system, in any version, and the roadmap says so
        rather than leaving it to be assumed.
      </p>
    </ExampleOf>
  );
}

export function WatchlistExample() {
  return (
    <ExampleOf what="a watchlist note">
      <ExampleField k="token" v="DEMORUNNERxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" />
      <ExampleField k="lore" v="“the mascot everyone already knew”" />
      <ExampleField
        k="why it ran, as claimed"
        v="borrowed identity travels further than invented identity — untested"
      />
      <ExampleField k="claimed market cap" v="180–230M" />
      <ExampleField k="measured market cap" v="$222,600,000" />
      <ExampleField k="priced in" v="DEMOGAS — gas" />
      <p className="mt-3 text-grey">
        The claim and the measurement sit side by side and are never blended: on one real note
        they disagreed by more than fifty percent. Every token here is dropped from every dataset
        by name — a list written after seeing which ones ran is a list of survivors, and a rate
        computed over survivors is a fact about whoever wrote the list.
      </p>
    </ExampleOf>
  );
}

export function PairingExample() {
  return (
    <ExampleOf what="a pairing">
      <ExampleField k="token" v="DEMOMEMExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" />
      <ExampleField k="quoted in" v="DEMOEQ — a tokenised share" />
      <ExampleField k="kind" v="tokenised-equity" />
      <ExampleField k="found by" v="equity-quote" />
      <ExampleField k="liquidity" v="$412,000" />
      <p className="mt-3 text-grey">
        The kind is read from the quote token&rsquo;s name, never its symbol: a symbol is free
        text anyone can mint, and claiming a famous ticker costs nothing.
      </p>
    </ExampleOf>
  );
}
