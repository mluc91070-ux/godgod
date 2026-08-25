import { api } from "@/lib/api";
import type { Status } from "@/lib/types";

/**
 * Persistent honesty strip. If the API is unreachable it says so; if the
 * system is serving fixtures it says DEMO MODE on every page.
 */
export default async function StatusBar() {
  const result = await api<Status>("/api/status");

  if (!result.ok) {
    return (
      <div className="flex flex-wrap items-center gap-4 border-b border-line px-6 py-2 text-[10px] uppercase tracking-widest text-muted">
        <span className="text-violet">api unreachable</span>
        <span className="normal-case tracking-normal">{result.error}</span>
      </div>
    );
  }

  const { mode, state, phase, version } = result.data;

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line px-6 py-2 text-[10px] uppercase tracking-widest text-muted">
      {mode.demo_mode ? (
        <span className="border border-lime/50 px-2 py-[1px] text-lime">demo mode</span>
      ) : (
        <span className="border border-line px-2 py-[1px] text-bone">live</span>
      )}
      <span>
        state <span className="text-bone">{state}</span>
      </span>
      <span>
        autonomy <span className="text-bone">L{mode.autonomy_level}</span> {mode.autonomy_label}
      </span>
      <span>
        x <span className="text-bone">{mode.x_mode}</span>
      </span>
      <span>
        wallet execution <span className="text-bone">off</span>
      </span>
      <span className="normal-case tracking-normal text-muted">{phase}</span>
      <span className="ml-auto">v{version}</span>
    </div>
  );
}
