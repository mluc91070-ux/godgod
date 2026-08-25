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

      <Section title="what runs today" note="PHASE 1–3">
        <ul className="space-y-1 text-muted">
          <li>— database schema and migrations for the full research chain</li>
          <li>— read API over observations, hypotheses, experiments, traces, patterns, memory</li>
          <li>— memory: store, embed, rank by cosine, neighbours, cluster, digest</li>
          <li>— observation pipeline: ingest, filter, score, ten anomaly detectors</li>
          <li>— demo mode serving fixtures, every row flagged is_demo</li>
          <li>— draft approval with an operator token; publishing deliberately refuses</li>
          <li>— this frontend</li>
        </ul>
      </Section>

      <Section title="what does not run yet">
        <ul className="space-y-1 text-muted">
          <li>— PHASE 4–6 hypothesis, experiment and critic engines</li>
          <li>— every external integration: model calls, X, Solana RPC (scheduled last)</li>
          <li>— PHASE 9 SSE streaming; the terminal is polled on load</li>
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
