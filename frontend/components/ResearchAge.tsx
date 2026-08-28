import { fmtTime } from "@/lib/api";
import { getStatus } from "@/lib/status";

/**
 * Why a research page is empty, answered in dates rather than adjectives.
 *
 * "No results yet" is true and useless. What a reader needs is when the
 * measuring started, how long the longest question needs to watch a token
 * before it can be answered, and whether the loop is still running — three
 * facts that turn an empty page from a broken one into an honest one.
 *
 * Every number here is read from `/api/status`; none is written down.
 */
export default async function ResearchAge({ what }: { what: string }) {
  const result = await getStatus();
  if (!result.ok) return null;

  const { collection, research } = result.data;
  const since = collection.measuring_since;
  const horizons = research.horizons_hours ?? [];
  const longest = horizons.length ? horizons[horizons.length - 1] : null;

  const hours = since
    ? Math.max(0, Math.floor((Date.now() - Date.parse(since)) / 3_600_000))
    : null;

  return (
    <div className="border border-line p-6 text-muted">
      <p>
        no {what} yet.{" "}
        {since ? (
          <>
            the first real measurement was stored {fmtTime(since)}
            {hours !== null ? ` — ${hours} hours ago` : null}
            {collection.running_since ? (
              <>, and the system has been writing about its own work since{" "}
                {fmtTime(collection.running_since)}</>
            ) : null}
            .
          </>
        ) : (
          <>nothing has been measured yet, so there is nothing to ask about.</>
        )}
      </p>

      {longest !== null ? (
        <p className="mt-3">
          questions are asked over {horizons.map((hour) => `${hour}h`).join(", ")}. a token has
          to be watched for the whole of a question&apos;s window and then its horizon before it
          can answer one, so the {longest}h questions are the last to fill.
        </p>
      ) : null}

      <p className="mt-3 text-[11px]">
        {collection.scheduler_running
          ? `measuring on its own clock every ${Math.round(
              (collection.scheduler_interval_seconds ?? 900) / 60,
            )} minutes — this page fills itself.`
          : "the collection loop is not running, so this page will not fill on its own."}
      </p>
    </div>
  );
}
