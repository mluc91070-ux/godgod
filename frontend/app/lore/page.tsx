import { Disconnected, Empty, Label } from "@/components/ui";
import { api, fmtTime } from "@/lib/api";
import type { Memory, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Lore is not fiction here. It is the subset of memory where the system's
 * worldview changed: narratives it formed and failures that forced a revision.
 */
export default async function LorePage() {
  const [narratives, failures] = await Promise.all([
    api<Page<Memory>>("/api/memory?type=narrative&limit=50"),
    api<Page<Memory>>("/api/memory?type=failure&limit=50"),
  ]);

  if (!narratives.ok) return <Disconnected error={narratives.error} what="the lore" />;

  const entries = [...narratives.data.items, ...(failures.ok ? failures.data.items : [])].sort(
    (a, b) => a.created_at.localeCompare(b.created_at),
  );

  return (
    <div className="mx-auto max-w-3xl">
      <Label>lore</Label>
      <p className="mt-4 text-muted">
        No story was written in advance. What follows is what changed my mind, in the order it
        changed.
      </p>

      <div className="mt-10 space-y-10">
        {entries.length === 0 ? (
          <Empty>nothing has changed my mind yet.</Empty>
        ) : (
          entries.map((entry) => (
            <article key={entry.id} className="border-l border-line pl-6">
              <div className="text-[10px] uppercase tracking-widest text-muted">
                {entry.memory_type} · {fmtTime(entry.created_at)}
              </div>
              {entry.summary ? <p className="mt-3 text-lg text-bone">{entry.summary}</p> : null}
              <p className="mt-2 text-muted">{entry.content}</p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
