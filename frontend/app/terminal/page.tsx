import LiveTerminal from "@/components/LiveTerminal";
import { Disconnected, Label } from "@/components/ui";
import { API_URL, api } from "@/lib/api";
import type { Page, StreamEvent, SystemEvent } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TerminalPage() {
  const result = await api<Page<SystemEvent>>("/api/events?limit=100");

  if (!result.ok) return <Disconnected error={result.error} what="the event log" />;

  // Rendered on the server so the page is readable before the stream connects,
  // and still readable if it never does.
  const initial: StreamEvent[] = [...result.data.items].reverse().map((event) => ({
    ...event,
    ref_type: null,
    ref_id: null,
    is_demo: true,
    replayed: true,
  }));

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>terminal</Label>
        <span className="text-[10px] text-muted">{result.data.total} events recorded</span>
      </div>

      <div className="mt-6">
        <LiveTerminal apiUrl={API_URL} initial={initial} />
      </div>

      <p className="mt-4 text-[11px] text-muted">
        server-sent events over the rows the system writes as it works. history is marked as
        replay; only what arrives after you connect is marked new. the stream carries no
        prediction of what is about to happen — if it is quiet, the system is quiet.
      </p>
    </div>
  );
}
