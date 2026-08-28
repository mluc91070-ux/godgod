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

  const { mode, state, phase, version, collection } = result.data;
  // Read from the running task, never from the setting that asked for it.
  const beating = collection.scheduler_running;

  return (
    <div className="border-b border-line px-4 py-2.5 sm:px-6">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
        {mode.demo_mode ? (
          <span className="flex items-center gap-1.5 text-amber">
            <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
            demo mode
          </span>
        ) : (
          <span
            className="flex items-center gap-1.5 text-bone"
            title={
              beating
                ? `measuring every ${Math.round(
                    (collection.scheduler_interval_seconds ?? 900) / 60,
                  )} minutes`
                : "the collection loop is not running"
            }
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                beating ? "live-dot bg-bone" : "bg-amber"
              }`}
              aria-hidden
            />
            live
            {beating ? null : <span className="text-amber">· loop stopped</span>}
          </span>
        )}
        <Dot />
        <span className="text-bone">{state}</span>

        {/* One block, because these three are one fact: what this deployment
            is allowed to do. Read as three loose items they invited the
            question "allowed by what?" on every page. */}
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 border border-line px-2 py-[2px]">
          <span className="text-muted">execution</span>
          <span className="text-bone">
            L{mode.autonomy_level} {mode.autonomy_label}
          </span>
          <Dot />
          <span>
            x <span className="text-bone">{mode.x_stage}</span>
          </span>
          <Dot />
          <span>
            {mode.wallet_execution_enabled ? (
              <span className="text-amber">wallet execution on</span>
            ) : (
              "no execution"
            )}
          </span>
        </span>

        <span className="ml-auto tabular-nums">v{version}</span>
      </div>

      <p className="mt-1.5 max-w-3xl text-[11px] leading-snug text-muted">{phase}</p>
    </div>
  );
}
