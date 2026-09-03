import { AgentExample } from "@/components/examples";
import { Field, Label, Nothing } from "@/components/ui";
import { api } from "@/lib/api";
import type { AgentInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const result = await api<AgentInfo[]>("/api/agents");

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-4xl">
        <Label>agents</Label>
        <div className="mt-6">
          <Nothing
            what="the agent roster"
            unreachable
            error={result.error}
            because=""
            needs={[
              "which parts of this system call a model and which are engines with none",
              "a deterministic engine is never reported as implemented — doing the same job is not the same claim",
              "the researcher and the statistics stay deterministic on purpose: a hypothesis comes from a template so nothing reads the data before choosing what to claim about it",
            ]}
          >
            <AgentExample />
          </Nothing>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>agents</Label>
        <span className="text-[10px] text-muted">
          {result.data.filter((agent) => agent.implemented).length} of {result.data.length} have a
          model behind them
        </span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        each agent answers exactly one question and holds only the tools that question requires.
        the badge says how the job is done today, not how important it is.
      </p>

      <dl className="mt-4 max-w-2xl space-y-1 text-muted">
        <div className="flex gap-3">
          <dt className="w-24 shrink-0 text-amber">model</dt>
          <dd>a model call runs, and its answer is checked before anything is stored.</dd>
        </div>
        <div className="flex gap-3">
          <dt className="w-24 shrink-0 text-magenta">beta</dt>
          <dd>the same, recently added and still being watched.</dd>
        </div>
        <div className="flex gap-3">
          <dt className="w-24 shrink-0">deterministic</dt>
          <dd>no model at all — an engine under app/services does it.</dd>
        </div>
      </dl>

      <p className="mt-4 max-w-2xl text-muted">
        the last two are deliberate, not unfinished. a hypothesis is written from a template so
        that nothing reads the data before deciding what to claim about it, and the statistics
        have one right answer. a model in either place would trade a guarantee for a sentence.
      </p>

      <p className="mt-3 max-w-2xl text-muted">
        the two that do run are constrained rather than trusted: the reviewer and the critic can
        only make a verdict harsher, never lighter, and the observer describes an anomaly a
        detector already found rather than finding one. every model call is recorded with its
        tokens and its cost, and refused before it happens if the day’s budget cannot account
        for it.
      </p>

      <div className="mt-8 space-y-8">
        {result.data.map((agent) => (
          <article key={agent.id} className="border-t border-line pt-4">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="tracking-widest">{agent.name}</h2>
              <span
                className={`border px-2 py-[2px] text-[10px] tracking-widest ${
                  agent.stage === "beta"
                    ? "border-magenta/40 text-magenta"
                    : agent.stage === "model"
                      ? "border-amber/40 text-amber"
                      : "border-line text-muted"
                }`}
              >
                {agent.stage === "beta" ? "beta testing" : agent.stage}
              </span>
            </div>
            <p className="mt-2 text-bone">{agent.question}</p>
            <div className="mt-3">
              <Field k="role" v={agent.role} />
              <Field k="inputs" v={agent.inputs?.join(", ")} />
              <Field k="outputs" v={agent.outputs?.join(", ")} />
              <Field k="tools" v={agent.allowed_tools?.join(", ")} />
              <Field k="model role" v={agent.model_role} />
              <Field
                k="model behind it"
                v={agent.implemented ? "yes" : "no — a deterministic engine does this job"}
              />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
