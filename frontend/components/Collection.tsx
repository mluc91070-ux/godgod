import { Label } from "@/components/ui";
import { fmtInt, fmtTime } from "@/lib/api";
import type { Status } from "@/lib/types";

/**
 * What the live collectors have gathered so far.
 *
 * Shown while the site still serves the demo dataset, because the collectors
 * run regardless and hiding that would make real work invisible. The progress
 * bar measures distance to the point where a detector can speak — not
 * completion of anything, and it says so.
 */
export default function Collection({ status }: { status: Status }) {
  const c = status.collection;
  const ratio = Math.min(1, c.deepest_history / Math.max(1, c.needed_to_observe));

  return (
    <section className="border-t border-line pt-4">
      <div className="flex items-baseline justify-between gap-4">
        <Label>live collection</Label>
        <span className="text-[10px] text-muted">
          {c.observing_live ? "researching real measurements" : "measuring; still serving fixtures"}
        </span>
      </div>

      <div className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-3">
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">tokens measured</span>
          <span>{fmtInt(c.live_tokens)}</span>
        </div>
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">measurements</span>
          <span>{fmtInt(c.live_snapshots)}</span>
        </div>
        <div className="flex justify-between border-b border-line py-1">
          <span className="text-muted">social posts</span>
          <span>{fmtInt(c.live_posts)}</span>
        </div>
      </div>

      {!c.observing_live ? (
        <div className="mt-5">
          <div className="flex justify-between text-[10px] uppercase tracking-widest text-muted">
            <span>history on the most-measured token</span>
            <span>
              {c.deepest_history} of {c.needed_to_observe}
            </span>
          </div>
          <div className="mt-2 h-[3px] w-full bg-line">
            <div className="h-full bg-amber" style={{ width: `${ratio * 100}%` }} />
          </div>
          <p className="mt-3 text-[11px] text-muted">
            a detector needs {c.needed_to_observe} measurements of the same token before it can
            call anything unusual. one measurement is not a trend, so until then the research
            below runs on a synthetic dataset and says so on every row. this bar is distance to
            that threshold, not progress toward a result.
          </p>
        </div>
      ) : null}

      <p className="mt-4 text-[11px] text-muted">
        last chain collection {fmtTime(c.last_chain_run_at)}
        {c.last_x_run_at ? ` · last social collection ${fmtTime(c.last_x_run_at)}` : null}
      </p>
    </section>
  );
}
