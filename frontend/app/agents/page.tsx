import { Disconnected, Field, Label } from "@/components/ui";
import { api } from "@/lib/api";
import type { AgentInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const result = await api<AgentInfo[]>("/api/agents");

  if (!result.ok) return <Disconnected error={result.error} what="the agent roster" />;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>agents</Label>
        <span className="text-[10px] text-muted">
          {result.data.filter((agent) => agent.implemented).length} of {result.data.length}{" "}
          implemented
        </span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        each agent answers exactly one question and holds only the tools that question requires.
        an agent marked <span className="text-bone">not implemented</span> does not run — the
        roster describes the architecture, not a capability.
      </p>

      <p className="mt-3 max-w-2xl text-muted">
        the writer and the reviewer have a model behind them. the other four do not: their work
        is done by deterministic engines under <code className="text-bone">app/services</code>,
        which is a different thing and is not counted as an agent here. every model call is
        recorded with its tokens and its cost, and refused before it happens if the day’s
        budget cannot account for it.
      </p>

      <div className="mt-8 space-y-8">
        {result.data.map((agent) => (
          <article key={agent.id} className="border-t border-line pt-4">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="tracking-widest">{agent.name}</h2>
              <span
                className={`border px-2 py-[2px] text-[10px] tracking-widest ${
                  agent.implemented ? "border-amber/40 text-amber" : "border-line text-muted"
                }`}
              >
                {agent.implemented ? "implemented" : "not implemented"}
              </span>
            </div>
            <p className="mt-2 text-bone">{agent.question}</p>
            <div className="mt-3">
              <Field k="role" v={agent.role} />
              <Field k="inputs" v={agent.inputs?.join(", ")} />
              <Field k="outputs" v={agent.outputs?.join(", ")} />
              <Field k="tools" v={agent.allowed_tools?.join(", ")} />
              <Field k="model role" v={agent.model_role} />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
