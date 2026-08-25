import { Disconnected, Empty, Label, Tag } from "@/components/ui";
import { api, fmt, fmtTime } from "@/lib/api";
import type { Memory, MemorySearch, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ q?: string }> };

export default async function MemoryPage({ searchParams }: Props) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();

  const result = query
    ? await api<MemorySearch>(`/api/memory/search?q=${encodeURIComponent(query)}&limit=50`)
    : await api<Page<Memory>>("/api/memory?limit=50");

  if (!result.ok) return <Disconnected error={result.error} what="memory" />;

  const items = result.data.items;
  const method = "method" in result.data ? result.data.method : "listing";
  const semantic = "semantic" in result.data ? result.data.semantic : false;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>memory</Label>
        <span className="text-[10px] text-muted">
          {result.data.total} stored · {method} · semantic {semantic ? "on" : "off (PHASE 2)"}
        </span>
      </div>

      <form action="/memory" className="mt-6 flex gap-3 border border-line p-3">
        <input
          type="search"
          name="q"
          defaultValue={query}
          placeholder="search what i remember"
          className="w-full bg-transparent text-bone outline-none placeholder:text-muted"
        />
        <button type="submit" className="text-[10px] uppercase tracking-widest text-muted hover:text-lime">
          search
        </button>
      </form>

      <div className="mt-6 space-y-5">
        {items.length === 0 ? (
          <Empty>
            nothing matches “{query}”. i am not going to invent a memory to fill the gap.
          </Empty>
        ) : (
          items.map((memory) => (
            <article key={memory.id} className="border-t border-line pt-4">
              <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                <Tag value={memory.memory_type} />
                <span>confidence {fmt(memory.confidence)}</span>
                <span>{fmtTime(memory.created_at)}</span>
                {memory.source ? <span>source {memory.source}</span> : null}
              </div>
              {memory.summary ? <p className="mt-3 text-bone">{memory.summary}</p> : null}
              <p className="mt-2 text-muted">{memory.content}</p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
