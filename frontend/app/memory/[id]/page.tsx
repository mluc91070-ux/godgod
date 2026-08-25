import Link from "next/link";
import { notFound } from "next/navigation";

import { Disconnected, Empty, Field, Label, Section, Tag } from "@/components/ui";
import { api, fmt, fmtTime } from "@/lib/api";
import type { Memory, MemoryCluster, MemorySearch } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export default async function MemoryDetailPage({ params }: Props) {
  const { id } = await params;
  const result = await api<Memory>(`/api/memory/${id}`);

  if (!result.ok) {
    if (result.error.startsWith("404")) notFound();
    return <Disconnected error={result.error} what="this memory" />;
  }

  const memory = result.data;
  const [related, cluster] = await Promise.all([
    api<MemorySearch>(`/api/memory/${id}/related?limit=8`),
    api<MemoryCluster>(`/api/memory/${id}/cluster?limit=12`),
  ]);

  return (
    <article className="mx-auto max-w-4xl space-y-10">
      <header>
        <Link href="/memory" className="text-[10px] uppercase tracking-widest text-muted hover:text-bone">
          ← memory
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Tag value={memory.memory_type} />
          <span className="text-[10px] uppercase tracking-widest text-muted">
            {fmtTime(memory.created_at)}
          </span>
        </div>
        {memory.summary ? <h1 className="mt-4 text-lg">{memory.summary}</h1> : null}
        <p className="mt-3 text-muted">{memory.content}</p>
      </header>

      <Section title="provenance">
        <Field k="source" v={memory.source} />
        <Field k="confidence" v={fmt(memory.confidence)} />
        <Field k="derived from" v={memory.ref_type ? `${memory.ref_type} ${memory.ref_id ?? "—"}` : "—"} />
        <Field k="embedding model" v={memory.embedding_model} />
        <Field k="vector stored" v={memory.has_vector ? "yes" : "no"} />
        <Field k="times recalled" v={String(memory.access_count)} />
      </Section>

      <Section
        title="neighbours"
        note={related.ok ? `${related.data.method} · lexical vectors` : undefined}
      >
        {!related.ok ? (
          <Empty>neighbours unavailable: {related.error}</Empty>
        ) : related.data.items.length === 0 ? (
          <Empty>nothing else in memory is close to this one.</Empty>
        ) : (
          <ul className="space-y-3">
            {related.data.items.map(({ memory: neighbour, score }) => (
              <li key={neighbour.id} className="border-b border-line pb-3">
                <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                  <Tag value={neighbour.memory_type} />
                  <span className="text-lime">{fmt(score, 3)}</span>
                  <Link href={`/memory/${neighbour.id}`} className="hover:text-bone">
                    open →
                  </Link>
                </div>
                <p className="mt-2 text-muted">{neighbour.summary ?? neighbour.content}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {cluster.ok ? (
        <Section title="cluster" note={`threshold ${fmt(cluster.data.threshold, 2)}`}>
          <p className="text-[11px] text-muted">
            {cluster.data.items.length} memories sit within cosine {fmt(cluster.data.threshold, 2)}{" "}
            of this one. Single pass, no transitive expansion: this means “close to this”, not
            “somehow connected”.
          </p>
          <ul className="mt-4 space-y-1 text-[11px]">
            {cluster.data.items.map(({ memory: item, score }) => (
              <li key={item.id} className="flex gap-3">
                <span className="w-12 text-lime">{fmt(score, 3)}</span>
                <span className="w-24 text-muted">{item.memory_type.toLowerCase()}</span>
                <span className="min-w-0 flex-1 truncate text-muted">
                  {item.summary ?? item.content}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </article>
  );
}
