import { Disconnected, Label, Tag } from "@/components/ui";
import { api, fmt, fmtTime } from "@/lib/api";
import type { Observation, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ObservePage() {
  const result = await api<Page<Observation>>("/api/observations?limit=50");

  if (!result.ok) return <Disconnected error={result.error} what="observations" />;

  const { items, total } = result.data;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>observations</Label>
        <span className="text-[10px] text-muted">{total} recorded</span>
      </div>

      <div className="mt-6 space-y-6">
        {items.map((observation) => (
          <article key={observation.id} className="border-t border-line pt-4">
            <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
              <span>#{observation.seq ?? "—"}</span>
              <Tag value={observation.kind} />
              <span>{fmtTime(observation.observed_at)}</span>
              <span>novelty {fmt(observation.novelty_score)}</span>
              <span>importance {fmt(observation.importance)}</span>
              {observation.llm_reviewed ? <span>model-reviewed</span> : <span>filter only</span>}
            </div>

            <p className="mt-3">{observation.summary}</p>

            {observation.subject_ref ? (
              <p className="mt-2 break-all text-[11px] text-muted">
                subject {observation.subject_type} {observation.subject_ref}
              </p>
            ) : null}

            {observation.payload ? (
              <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
                {Object.entries(observation.payload).map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <dt>{key}</dt>
                    <dd className="text-bone">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
