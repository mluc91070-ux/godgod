import { notFound } from "next/navigation";

import { ExperimentExample } from "@/components/examples";
import { Field, Label, Nothing, Section, Tag } from "@/components/ui";
import { api, fmt, fmtInt, fmtTime } from "@/lib/api";
import type { Experiment, Page, Trace } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export default async function ExperimentPage({ params }: Props) {
  const { id } = await params;
  const result = await api<Experiment>(`/api/experiments/${id}`);

  if (!result.ok) {
    if (result.error.startsWith("404")) notFound();
    return (
      <div className="mx-auto max-w-4xl">
        <Label>experiment</Label>
        <div className="mt-6">
          <Nothing
            what="this experiment"
            unreachable
            error={result.error}
            because=""
            needs={[
              "the dataset this question was run against, hashed so the run can be repeated exactly",
              "every row that could not be built, counted under a named reason",
              "the critic's checks, which can only make the verdict stricter and never lighter",
            ]}
          >
            <ExperimentExample />
          </Nothing>
        </div>
      </div>
    );
  }

  const experiment = result.data;
  const outcome = experiment.results?.[0];
  const hypothesis = experiment.hypothesis;

  const traces = await api<Page<Trace>>("/api/traces?limit=50");
  const trace = traces.ok
    ? traces.data.items.find((item) => item.experiment_id === experiment.id)
    : undefined;

  return (
    <article className="mx-auto max-w-4xl space-y-10">
      <header>
        <Label>experiment #{String(experiment.seq ?? 0).padStart(6, "0")}</Label>
        <h1 className="mt-3 text-lg">{experiment.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Tag value={experiment.status} />
          {outcome ? <Tag value={outcome.outcome} /> : null}
          {outcome ? <Tag value={outcome.critic_verdict} /> : null}
        </div>
      </header>

      {hypothesis ? (
        <Section title="question">
          <p className="text-bone">{hypothesis.question}</p>
          <p className="mt-2 text-muted">{hypothesis.statement}</p>
          <div className="mt-4">
            <Field k="population" v={hypothesis.population} />
            <Field k="sample" v={hypothesis.sample_definition} />
            <Field k="timeframe" v={hypothesis.timeframe} />
            <Field k="baseline" v={hypothesis.baseline} />
            <Field
              k="falsified if"
              v={<span className="text-amber">{hypothesis.falsification_condition}</span>}
            />
          </div>
        </Section>
      ) : null}

      <Section title="dataset" note="reproducibility">
        <Field k="version" v={experiment.dataset_version} />
        <Field k="hash" v={<span className="break-all text-[11px]">{experiment.dataset_hash}</span>} />
        <Field k="sample size" v={fmtInt(experiment.sample_size)} />
        <Field k="train" v={experiment.train_period} />
        <Field k="validation" v={experiment.validation_period} />
        <Field k="out of sample" v={experiment.out_of_sample_period} />
        <Field k="features" v={experiment.features?.join(", ")} />
      </Section>

      <Section title="method">
        <p className="text-muted">{experiment.method}</p>
        {experiment.parameters ? (
          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
            {Object.entries(experiment.parameters).map(([key, value]) => (
              <div key={key} className="flex gap-2">
                <dt>{key}</dt>
                <dd className="text-bone">{JSON.stringify(value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </Section>

      {outcome ? (
        <>
          <Section title="result">
            <p>{outcome.summary}</p>
            <div className="mt-4">
              <Field k="effect size" v={fmt(outcome.effect_size)} />
              <Field k="p value" v={fmt(outcome.p_value)} />
              <Field k="confidence" v={fmt(outcome.confidence)} />
            </div>
            {outcome.metrics ? (
              <dl className="mt-4 grid gap-x-6 gap-y-1 text-[11px] text-muted sm:grid-cols-2">
                {Object.entries(outcome.metrics).map(([key, value]) => (
                  <div key={key} className="flex justify-between border-b border-line py-1">
                    <dt>{key}</dt>
                    <dd className="text-bone">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </Section>

          <Section title="critic" note="a hypothesis cannot become supported without this gate">
            <div className="flex items-center gap-3">
              <Tag value={outcome.critic_verdict} />
            </div>
            {outcome.critic_notes ? <p className="mt-3 text-muted">{outcome.critic_notes}</p> : null}
            {outcome.critic_checks ? (
              <dl className="mt-4 grid gap-x-6 text-[11px] sm:grid-cols-2">
                {Object.entries(outcome.critic_checks).map(([key, value]) => (
                  <div key={key} className="flex justify-between border-b border-line py-1">
                    <dt className="text-muted">{key}</dt>
                    <dd className={value === "PASS" ? "text-amber" : "text-magenta"}>{value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </Section>

          <Section title="limitations">
            <p className="text-muted">{outcome.limitations ?? experiment.limitations ?? "—"}</p>
            {experiment.is_demo ? (
              <p className="mt-3 text-amber">
                demo data. this experiment describes fixtures, not any real asset.
              </p>
            ) : null}
          </Section>
        </>
      ) : (
        <Section title="result">
          <p className="text-muted">no result recorded yet.</p>
        </Section>
      )}

      {trace ? (
        <Section title={`trace #${String(trace.seq ?? 0).padStart(6, "0")}`} note="immutable">
          <ol className="space-y-2">
            {trace.steps.map((step) => (
              <li key={step.id} className="flex flex-col gap-0.5 sm:grid sm:grid-cols-[8rem_9rem_1fr] sm:gap-3">
                <span className="text-muted">{fmtTime(step.occurred_at).slice(11)}</span>
                <span className="text-[10px] uppercase tracking-widest text-bone">{step.kind}</span>
                <span className="text-muted">{step.summary}</span>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}
    </article>
  );
}
