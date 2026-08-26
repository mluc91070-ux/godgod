import Link from "next/link";
import { notFound } from "next/navigation";

import { Disconnected, Empty, Field, Label, Section, Tag } from "@/components/ui";
import { api, fmt, fmtInt, fmtTime } from "@/lib/api";
import type { Hypothesis, Memory, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export default async function HypothesisPage({ params }: Props) {
  const { id } = await params;
  const result = await api<Hypothesis>(`/api/hypotheses/${id}`);

  if (!result.ok) {
    if (result.error.startsWith("404")) notFound();
    return <Disconnected error={result.error} what="this hypothesis" />;
  }

  const hypothesis = result.data;
  const variables = hypothesis.variables ?? {};
  const consulted = Array.isArray(variables.memory_consulted)
    ? (variables.memory_consulted as string[])
    : [];

  // What was already known when the question was written. Fetched by id, so the
  // page shows the rows that were actually consulted rather than a summary.
  const memories = await Promise.all(
    consulted.slice(0, 8).map((memoryId) => api<Memory>(`/api/memory/${memoryId}`)),
  );
  const recalled = memories.flatMap((item) => (item.ok ? [item.data] : []));

  const experiments = hypothesis.experiments ?? [];

  return (
    <article className="mx-auto max-w-4xl space-y-10">
      <header>
        <Label>hypothesis #{String(hypothesis.seq ?? 0).padStart(6, "0")}</Label>
        <h1 className="mt-3 text-lg">{hypothesis.question}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Tag value={hypothesis.status} />
          <span className="text-[10px] uppercase tracking-widest text-muted">
            confidence {fmt(hypothesis.confidence)}
          </span>
          <span className="text-[10px] uppercase tracking-widest text-muted">
            written {fmtTime(hypothesis.created_at)}
          </span>
        </div>
        <p className="mt-4 text-muted">{hypothesis.statement}</p>
      </header>

      <Section title="how it can be wrong" note="written before the data was seen">
        <Field
          k="falsified if"
          v={<span className="text-lime">{hypothesis.falsification_condition}</span>}
        />
        <Field k="expected" v={hypothesis.expected_result} />
        <Field k="baseline" v={hypothesis.baseline} />
      </Section>

      <Section title="design">
        <Field k="population" v={hypothesis.population} />
        <Field k="sample" v={hypothesis.sample_definition} />
        <Field k="timeframe" v={hypothesis.timeframe} />
        {Object.entries(variables)
          .filter(([key]) => key !== "memory_consulted")
          .map(([key, value]) => (
            <Field
              key={key}
              k={key.replace(/_/g, " ")}
              v={typeof value === "string" ? value : JSON.stringify(value)}
            />
          ))}
      </Section>

      <Section
        title="what was already known"
        note={`${consulted.length} memories retrieved before this question was written`}
      >
        {recalled.length === 0 ? (
          <p className="text-muted">
            {consulted.length === 0
              ? "nothing in memory matched this subject. the question was written from the anomaly alone."
              : "the memories consulted are no longer retrievable by id."}
          </p>
        ) : (
          <ul className="space-y-3">
            {recalled.map((memory) => (
              <li key={memory.id}>
                <Link href={`/memory/${memory.id}`} className="text-muted hover:text-lime">
                  <span className="text-[10px] uppercase tracking-widest">
                    {memory.memory_type}
                  </span>{" "}
                  {memory.summary ?? memory.content}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="experiments">
        {experiments.length === 0 ? (
          <Empty>this question has not been tested yet.</Empty>
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {experiments.map((experiment) => (
              <li key={experiment.id}>
                <Link
                  href={`/experiments/${experiment.id}`}
                  className="grid grid-cols-[1fr_6rem_7rem] items-center gap-4 py-3 hover:text-lime"
                >
                  <span>{experiment.title}</span>
                  <span className="text-[11px] text-muted">
                    n={fmtInt(experiment.sample_size)}
                  </span>
                  <span className="flex justify-end">
                    <Tag value={experiment.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {hypothesis.is_demo ? (
        <p className="text-[11px] text-lime">
          demo data. this question was asked of fixtures, not of any real asset.
        </p>
      ) : null}
    </article>
  );
}
