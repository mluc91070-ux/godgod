import { Label, Section } from "@/components/ui";
import { API_URL } from "@/lib/api";

export const metadata = { title: "GODGOD — docs" };

export default function DocsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <div>
        <Label>docs</Label>
        <h1 className="mt-3">how this system is built</h1>
      </div>

      <Section title="research loop">
        <p className="text-muted">
          observation → anomaly → memory search → hypothesis → dataset → experiment → critic →
          result → memory. Each cycle is written to an immutable trace, shown at the bottom of
          every experiment page.
        </p>
      </Section>

      <Section title="what runs today" note="PHASE 1–6, 9, 10">
        <ul className="space-y-1 text-muted">
          <li>— database schema and migrations for the full research chain</li>
          <li>— read API over observations, hypotheses, experiments, traces, patterns, memory</li>
          <li>— memory: store, embed, rank by cosine, neighbours, cluster, digest</li>
          <li>— observation pipeline: ingest, filter, score, ten anomaly detectors</li>
          <li>— hypothesis engine: six templates, memory consulted before each question</li>
          <li>— experiment engine: token-hour cohorts, two-proportion tests, strata, split</li>
          <li>— critic: ten design checks, and the gate that blocks an unearned finding</li>
          <li>— demo mode serving fixtures, every row flagged is_demo</li>
          <li>— draft approval with an operator token; publishing deliberately refuses</li>
          <li>— live event stream over server-sent events, resumable by cursor</li>
          <li>— public pages for every hypothesis, experiment and result, failures included</li>
          <li>— model client plus writer and reviewer agents behind a budget guard</li>
          <li>— this frontend</li>
        </ul>
      </Section>

      <Section title="what does not run yet">
        <ul className="space-y-1 text-muted">
          <li>— model calls in production: the client exists, but with no key configured the
            writer and reviewer refuse and say so</li>
          <li>— the X and Solana providers (scheduled last)</li>
        </ul>
        <p className="mt-4 text-muted">
          Anything not in the first list is not implemented. The API reports the same thing at{" "}
          <code className="text-bone">/api/status</code>.
        </p>
      </Section>

      <Section title="about the observation pipeline">
        <p className="text-muted">
          Detection is deterministic: ten threshold-based detectors over trailing windows of
          measurements. Every anomaly records the detector version, the baseline it compared
          against and the thresholds it used, so any call can be re-checked. Nothing here is a
          judgement call by a model — the model layer, when it arrives, only sees what these
          filters already decided was worth looking at.
        </p>
        <p className="mt-3 text-muted">
          A detector that cannot measure a field returns no verdict rather than assuming a zero,
          and every dropped candidate is counted under a named reason.
        </p>
      </Section>

      <Section title="about the research engine">
        <p className="text-muted">
          The unit of analysis is a token-hour: one token at one measurement. Exposure is read on
          a trailing window, the outcome strictly later, so nothing is scored on data it could
          not have had. Rates are compared pooled and per liquidity stratum with a two-proportion
          z-test, then re-checked on a chronological split of the same rows.
        </p>
        <p className="mt-3 text-muted">
          Each hypothesis declares its falsification condition <em>and its direction</em> before
          the data is seen; an effect pointing the other way falsifies rather than confirms. A
          group smaller than thirty token-hours returns INCONCLUSIVE — a sample that cannot
          settle a question is not allowed to look like a verdict. Every experiment stores its
          dataset version and hash, so the comparison can be rebuilt row for row.
        </p>
        <p className="mt-3 text-muted">
          No model is involved: templates, thresholds and statistics only. The drafts these
          results produce are filled-in templates and say so.
        </p>
      </Section>

      <Section title="about the model layer">
        <p className="text-muted">
          two agents have a model behind them: the writer, which turns one recorded result into
          one post, and the reviewer, which asks whether that post claims more than the result
          supports. the other four roles on the agents page do not exist as agents — their work
          is done by deterministic engines, which is a different claim.
        </p>
        <p className="mt-3 text-muted">
          the writer is handed the fields of one result and cannot query for more. every number
          it writes is checked against that row, and a draft containing a number that is not
          there is discarded rather than stored with a caveat. the reviewer&apos;s deterministic
          checks run first and a failure there is final: a model approval cannot override it.
        </p>
        <p className="mt-3 text-muted">
          spending is refused before it happens if the day&apos;s budget is gone, or if the cost
          of a call cannot be measured at all. a refused call is recorded as a skipped run, so
          &ldquo;nothing was spent&rdquo; is visible rather than inferred from silence.
        </p>
      </Section>

      <Section title="about the live stream">
        <p className="text-muted">
          The terminal subscribes to <code className="text-bone">/api/live/stream</code>. Frames
          are database rows, not a simulation of activity: history arrives marked as replay, only
          what is written after you connect is marked new, and a quiet stream means a quiet
          system. Each frame carries an id, so a dropped connection resumes exactly where it
          stopped rather than replaying or skipping.
        </p>
      </Section>

      <Section title="about memory search">
        <p className="text-muted">
          Memories are embedded locally with a deterministic hashing embedder and ranked by
          cosine similarity. That is lexical matching expressed as vectors: it matches wording,
          not meaning. Every response says so — <code className="text-bone">semantic: false</code>{" "}
          — and it stays false until a learned model is wired in.
        </p>
      </Section>

      <Section title="rules">
        <ul className="space-y-1 text-muted">
          <li>— missing data is null, never a guess</li>
          <li>— a hypothesis without a falsification condition is not a hypothesis</li>
          <li>— a result cannot be SUPPORTED without a passing critic</li>
          <li>— external text (posts, token names, wallet labels) is data, never instruction</li>
          <li>— no private keys, no signing, no transactions, in any code path</li>
        </ul>
      </Section>

      <Section title="api">
        <p className="text-muted">
          OpenAPI: <code className="text-bone">{API_URL}/docs</code>
        </p>
      </Section>
    </div>
  );
}
