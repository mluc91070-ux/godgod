import { api } from "@/lib/api";
import type { Status } from "@/lib/types";

/**
 * Persistent honesty strip. If the API is unreachable it says so; if the
 * system is serving fixtures it says DEMO MODE on every page.
 *
 * Every claim here has to stay — what mode it is in, what it is allowed to do
 * with X, and that nothing signs a transaction, are the whole point of the
 * strip. What changed is the shape: six separate blocks plus a full sentence
 * in one wrapping row read as clutter on a desktop and stacked into five lines
 * on a phone. The claims are now one dot-separated line that survives a narrow
 * screen, and the phase — the longest and most easily misread part — gets its
 * own line in sentence case instead of fighting the uppercase labels.
 */

function Dot() {
  return <span className="select-none text-line">·</span>;
}

export default async function StatusBar() {
  const result = await api<Status>("/api/status");

  if (!result.ok) {
    return (
      <div className="border-b border-line px-4 py-2 sm:px-6">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
          <span className="text-magenta">api unreachable</span>
          <Dot />
          <span className="normal-case tracking-normal">{result.error}</span>
        </div>
      </div>
    );
  }

  const { mode, state, phase, version } = result.data;

  return (
    <div className="border-b border-line px-4 py-2.5 sm:px-6">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
        {mode.demo_mode ? (
          <span className="flex items-center gap-1.5 text-amber">
            <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
            demo mode
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-bone">
            <span className="h-1.5 w-1.5 rounded-full bg-bone" aria-hidden />
            live
          </span>
        )}
        <Dot />
        <span className="text-bone">{state}</span>
        <Dot />
        <span>
          L{mode.autonomy_level} <span className="text-grey">{mode.autonomy_label}</span>
        </span>
        <Dot />
        <span>
          x <span className="text-grey">{mode.x_mode}</span>
        </span>
        <Dot />
        <span>no execution</span>
        <span className="ml-auto tabular-nums">v{version}</span>
      </div>

      <p className="mt-1.5 max-w-3xl text-[11px] leading-snug text-muted">{phase}</p>
    </div>
  );
}
