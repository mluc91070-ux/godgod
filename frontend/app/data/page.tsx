import Collection from "@/components/Collection";
import { Disconnected, Field, Label, Section } from "@/components/ui";
import { api, fmtTime } from "@/lib/api";
import type { Attention, Page, Source, Status } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DataPage() {
  const [sources, status, attention] = await Promise.all([
    api<Source[]>("/api/sources"),
    api<Status>("/api/status"),
    api<Page<Attention>>("/api/attention?limit=20"),
  ]);

  if (!sources.ok) return <Disconnected error={sources.error} what="data sources" />;

  return (
    <div className="mx-auto max-w-4xl space-y-10">
      <div>
        <Label>data</Label>
        <p className="mt-4 max-w-2xl text-muted">
          Everything the system knows comes from the sources below. A measurement that no source
          provides is stored as null and displayed as “—”.
        </p>
      </div>

      {status.ok ? <Collection status={status.data} /> : null}

      {/* What people are looking up, which is the one thing a pool cannot say.
          Positions, not sentiment: a coin is in the ranking at a rank at a
          time. A coin the feed did not list has no row, so nothing here is
          this system inventing anyone's indifference. */}
      {attention.ok && attention.data.items.length > 0 ? (
        <Section
          title="attention"
          note="a search ranking, sampled on the same clock as the pool"
        >
          <p className="text-muted">
            Lower rank means more looked-up. A token absent from the ranking has no row —
            unranked is not ranked last. A row is tied to a token only on an exact contract
            address; a matching symbol is never a link.
          </p>
          <ul className="mt-4 divide-y divide-line">
            {attention.data.items.slice(0, 15).map((row) => (
              <li key={row.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-2">
                <span className="w-8 text-[11px] text-muted">#{row.rank}</span>
                <span className="text-bone">{row.symbol ?? row.ref}</span>
                <span className="text-[10px] uppercase tracking-widest text-muted">
                  {row.chain ?? "chain not reported"}
                </span>
                {row.token_id ? (
                  <span className="text-[10px] uppercase tracking-widest text-amber">
                    measured here
                  </span>
                ) : (
                  <span className="text-[10px] uppercase tracking-widest text-muted">
                    not measured here
                  </span>
                )}
                <span className="ml-auto text-[10px] text-muted">
                  {fmtTime(row.observed_at)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="sources">
        <div className="space-y-6">
          {sources.data.map((source) => (
            <article key={source.id}>
              <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                <span className="text-bone">{source.kind}</span>
                <span>{source.name}</span>
                <span>last used {fmtTime(source.last_used_at)}</span>
              </div>
              {source.description ? (
                <p className="mt-2 text-muted">{source.description}</p>
              ) : null}
            </article>
          ))}
        </div>
      </Section>

      {status.ok ? (
        <>
          <Section title="providers">
            {status.data.providers.map((provider) => (
              <Field
                key={provider.name}
                k={provider.name}
                v={
                  <span>
                    <span className={provider.configured ? "text-bone" : "text-muted"}>
                      {provider.configured ? "configured" : "not configured"}
                    </span>
                    <span className="text-muted"> · </span>
                    <span className={provider.implemented ? "text-amber" : "text-muted"}>
                      {provider.implemented ? "implemented" : "not implemented"}
                    </span>
                    {provider.note ? (
                      <span className="block text-[11px] text-muted">{provider.note}</span>
                    ) : null}
                  </span>
                }
              />
            ))}
          </Section>

          <Section title="memory subsystem">
            <Field k="embedding provider" v={status.data.memory.embedding_provider} />
            <Field k="embedding model" v={status.data.memory.embedding_model} />
            <Field k="dimensions" v={String(status.data.memory.embedding_dim)} />
            <Field k="ranking backend" v={status.data.memory.backend} />
            <Field
              k="semantic"
              v={
                status.data.memory.semantic ? (
                  "yes"
                ) : (
                  <span className="text-muted">
                    no — the current embedder matches wording, not meaning
                  </span>
                )
              }
            />
          </Section>

          <Section title="observation pipeline">
            <Field k="source" v={status.data.pipeline.source} />
            <Field
              k="source kind"
              v={status.data.pipeline.source_is_demo ? "synthetic fixtures" : "live"}
            />
            <Field k="window" v={`${status.data.pipeline.window_hours}h`} />
            <Field k="detectors" v={status.data.pipeline.detectors.join(", ")} />
            {/* Listed apart rather than hidden: these are real detectors with
                no data behind them, and counting them among the others would
                report ten working measurements where there are seven. */}
            {status.data.pipeline.detectors_without_a_source?.length ? (
              <Field
                k="detectors with no source"
                v={status.data.pipeline.detectors_without_a_source.join(", ")}
              />
            ) : null}
            <Field
              k="model in the loop"
              v={
                status.data.pipeline.llm_in_loop ? (
                  "yes"
                ) : (
                  <span className="text-muted">
                    no — detection is deterministic, thresholds are recorded on every anomaly
                  </span>
                )
              }
            />
            <Field k="last run" v={fmtTime(status.data.pipeline.last_run_at)} />
          </Section>

          <Section title="stored rows">
            {Object.entries(status.data.counts).map(([key, value]) => (
              <Field key={key} k={key} v={String(value)} />
            ))}
          </Section>
        </>
      ) : null}
    </div>
  );
}
