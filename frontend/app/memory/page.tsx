import Link from "next/link";

import { Disconnected, Empty, Label, Tag } from "@/components/ui";
import { api, fmt, fmtTime } from "@/lib/api";
import type { MemoryDigest, MemoryHit, MemorySearch, Page, Memory } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ q?: string }> };

export default async function MemoryPage({ searchParams }: Props) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();

  const [result, digestResult] = await Promise.all([
    query
      ? api<MemorySearch>(`/api/memory/search?q=${encodeURIComponent(query)}&limit=25`)
      : api<Page<Memory>>("/api/memory?limit=50"),
    api<MemoryDigest>("/api/memory/summary"),
  ]);

  if (!result.ok) return <Disconnected error={result.error} what="memory" />;

  const hits: MemoryHit[] = query
    ? (result.data as MemorySearch).items
    : (result.data as Page<Memory>).items.map((memory) => ({ score: 1, memory }));

  const search = query ? (result.data as MemorySearch) : null;
  const digest = digestResult.ok ? digestResult.data : null;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>memory</Label>
        <span className="text-[10px] text-muted">
          {search
            ? `${search.method} · ${search.total_candidates} candidates · semantic ${
                search.semantic ? "on" : "off"
              }`
            : `${(result.data as Page<Memory>).total} stored`}
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
        <button
          type="submit"
          className="text-[10px] uppercase tracking-widest text-muted hover:text-amber"
        >
          search
        </button>
      </form>

      {search ? (
        <p className="mt-3 text-[10px] uppercase tracking-widest text-muted">
          ranked by cosine over {search.embedding_model} vectors. lexical, not semantic — it
          matches wording, not meaning.
        </p>
      ) : null}

      {digest && !query ? (
        <section className="mt-8 border border-line p-4">
          <Label>digest</Label>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
            {Object.entries(digest.by_type).map(([type, count]) => (
              <span key={type}>
                {type.toLowerCase()} <span className="text-bone">{count}</span>
              </span>
            ))}
            <span>
              vectors <span className="text-bone">{digest.with_vectors}</span>/{digest.total}
            </span>
          </div>
          {digest.recurring_terms.length ? (
            <p className="mt-3 text-[11px] text-muted">
              recurring:{" "}
              {digest.recurring_terms.map(([term, count]) => (
                <span key={term} className="text-bone">
                  {term}
                  <span className="text-muted">·{count} </span>
                </span>
              ))}
            </p>
          ) : null}
          <p className="mt-3 text-[10px] text-muted">{digest.note}</p>
        </section>
      ) : null}

      <div className="mt-8 space-y-5">
        {hits.length === 0 ? (
          <Empty>
            nothing matches “{query}”. i am not going to invent a memory to fill the gap.
          </Empty>
        ) : (
          hits.map(({ memory, score }) => (
            <article key={memory.id} className="border-t border-line pt-4">
              <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                <Tag value={memory.memory_type} />
                {query ? <span className="text-amber">score {fmt(score, 3)}</span> : null}
                <span>confidence {fmt(memory.confidence)}</span>
                <span>{fmtTime(memory.created_at)}</span>
                {memory.access_count > 0 ? <span>recalled {memory.access_count}×</span> : null}
                <Link href={`/memory/${memory.id}`} className="ml-auto hover:text-bone">
                  neighbours →
                </Link>
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
