import { Disconnected, Field, Label, Tag } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { Hypothesis, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HypothesesPage() {
  const result = await api<Page<Hypothesis>>("/api/hypotheses?limit=50");

  if (!result.ok) return <Disconnected error={result.error} what="hypotheses" />;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>hypotheses</Label>
        <span className="text-[10px] text-muted">{result.data.total} recorded</span>
      </div>

      <div className="mt-6 space-y-10">
        {result.data.items.map((hypothesis) => (
          <article key={hypothesis.id}>
            <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
              <span>#{hypothesis.seq ?? "—"}</span>
              <Tag value={hypothesis.status} />
              <span>confidence {fmt(hypothesis.confidence)}</span>
            </div>

            <p className="mt-3 text-bone">{hypothesis.question}</p>
            <p className="mt-2 text-muted">{hypothesis.statement}</p>

            <div className="mt-4">
              <Field k="population" v={hypothesis.population} />
              <Field k="sample" v={hypothesis.sample_definition} />
              <Field k="timeframe" v={hypothesis.timeframe} />
              <Field k="baseline" v={hypothesis.baseline} />
              <Field k="expected" v={hypothesis.expected_result} />
              <Field
                k="falsified if"
                v={<span className="text-lime">{hypothesis.falsification_condition}</span>}
              />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
