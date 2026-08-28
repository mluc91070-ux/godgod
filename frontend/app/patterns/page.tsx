import { Disconnected, Empty, Label, Tag } from "@/components/ui";
import { api, fmt, fmtTime } from "@/lib/api";
import type { Page, Pattern } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function PatternsPage() {
  const result = await api<Page<Pattern>>("/api/patterns?limit=50");

  if (!result.ok) return <Disconnected error={result.error} what="patterns" />;

  const items = result.data.items;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>patterns</Label>
        <span className="text-[10px] text-muted">
          {items.filter((item) => item.status === "CONFIRMED").length} confirmed ·{" "}
          {items.filter((item) => item.status === "REJECTED").length} rejected
        </span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        a question that has been asked more than once, and what came back each time. two
        supporting results confirm it; one rejection is enough to mark it rejected, because a
        falsification rule written in advance does not get a second opinion.
      </p>

      <div className="mt-6 space-y-8">
        {items.length === 0 ? (
          <Empty>no pattern has survived testing yet.</Empty>
        ) : (
          items.map((pattern) => (
            <article key={pattern.id} className="border-t border-line pt-4">
              <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                <Tag value={pattern.status} />
                <span>support {pattern.support_count}</span>
                <span>contradictions {pattern.contradiction_count}</span>
                <span>confidence {fmt(pattern.confidence)}</span>
                <span>first seen {fmtTime(pattern.first_seen_at)}</span>
              </div>
              <h2 className="mt-3">{pattern.name}</h2>
              <p className="mt-2 text-muted">{pattern.description}</p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
