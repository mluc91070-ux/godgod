import { Disconnected, Label } from "@/components/ui";
import { api, clock } from "@/lib/api";
import type { Page, SystemEvent } from "@/lib/types";

export const dynamic = "force-dynamic";

const LEVEL_COLOR: Record<string, string> = {
  WARN: "text-violet",
  ERROR: "text-violet",
};

export default async function TerminalPage() {
  const result = await api<Page<SystemEvent>>("/api/events?limit=100");

  if (!result.ok) return <Disconnected error={result.error} what="the event log" />;

  const events = [...result.data.items].reverse();

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>terminal</Label>
        <span className="text-[10px] text-muted">
          {result.data.total} events · polled on load · SSE streaming lands in PHASE 9
        </span>
      </div>

      <div className="mt-6 border border-line p-4">
        {events.length === 0 ? (
          <p className="text-muted">no events recorded.</p>
        ) : (
          <ol className="space-y-1">
            {events.map((event) => (
              <li key={event.id} className="grid grid-cols-[5.5rem_11rem_1fr] gap-3">
                <span className="text-muted">{clock(event.occurred_at)}</span>
                <span className={LEVEL_COLOR[event.level] ?? "text-bone"}>{event.event_type}</span>
                <span className="text-muted">{event.message}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
