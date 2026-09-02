"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { clock } from "@/lib/api";
import type { StreamEvent } from "@/lib/types";

const LEVEL_COLOR: Record<string, string> = {
  WARN: "text-magenta",
  ERROR: "text-magenta",
};

const MAX_ROWS = 500;
/** The log is unbounded; a browser tab is not. Older rows stay in /api/events. */

type Connection = "connecting" | "open" | "closed" | "unsupported" | "refused";
/** `refused` is a stream that never opened once, as distinct from one that
 *  dropped and is retrying. EventSource does not report why, and the two look
 *  identical from inside the browser — but only one of them will ever recover,
 *  and calling both "reconnecting" describes a feed the page does not have. */

/**
 * The event log as it is written.
 *
 * Two things this component refuses to do: invent activity when the stream is
 * quiet, and present replayed history as if it had just happened. A quiet
 * system looks quiet here.
 */
export default function LiveTerminal({
  apiUrl,
  initial,
}: {
  apiUrl: string;
  initial: StreamEvent[];
}) {
  const [rows, setRows] = useState<StreamEvent[]>(initial);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [receivedLive, setReceivedLive] = useState(0);
  const [follow, setFollow] = useState(true);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      setConnection("unsupported");
      return;
    }

    const source = new EventSource(`${apiUrl}/api/live/stream`);
    let closed = false;
    let opened = false;
    let failures = 0;

    source.addEventListener("open", () => {
      opened = true;
      failures = 0;
      setConnection("open");
    });

    source.addEventListener("log", (message) => {
      const event = JSON.parse((message as MessageEvent).data) as StreamEvent;
      if (!event.replayed) setReceivedLive((count) => count + 1);
      setRows((current) => {
        if (current.some((row) => row.id === event.id)) return current;
        const next = [...current, event];
        return next.length > MAX_ROWS ? next.slice(next.length - MAX_ROWS) : next;
      });
    });

    // The server closes a connection once it ages out and tells us so; the
    // browser reconnects on its own with the last id it saw.
    source.addEventListener("close", () => setConnection("connecting"));

    // A stream that never opened is not a stream that dropped. EventSource
    // retries forever and the browser is not told why it failed, so the label
    // said "reconnecting" indefinitely on a page that could never connect —
    // which is the site describing a working feed it does not have.
    //
    // Measured on the live deployment: the api sent no
    // access-control-allow-origin for this site's own domain, so every open
    // was refused before it started, and the terminal read as merely quiet.
    source.onerror = () => {
      if (closed) return;
      failures += 1;
      setConnection(!opened && failures >= 3 ? "refused" : "connecting");
    };

    return () => {
      closed = true;
      source.close();
      setConnection("closed");
    };
  }, [apiUrl]);

  useEffect(() => {
    if (follow) bottom.current?.scrollIntoView({ block: "end" });
  }, [rows, follow]);

  const label = useMemo(() => {
    switch (connection) {
      case "open":
        return receivedLive > 0
          ? `streaming · ${receivedLive} live`
          : "streaming · nothing new yet";
      case "connecting":
        return "reconnecting";
      case "refused":
        return (
          "the stream never opened from this page — the log above is what was " +
          "loaded and is not advancing. the browser is not told why; the usual " +
          "cause is the api refusing this origin"
        );
      case "unsupported":
        return "no EventSource in this browser · showing the log as loaded";
      default:
        return "disconnected";
    }
  }, [connection, receivedLive]);

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3 text-[10px] text-muted">
        <span className="flex items-center gap-2">
          <span
            className={
              connection === "open"
                ? "inline-block h-[6px] w-[6px] bg-amber"
                : connection === "refused"
                  ? // Not the same grey as "quiet". A feed that cannot open is
                    // a fault, and it has to look like one.
                    "inline-block h-[6px] w-[6px] bg-magenta"
                  : "inline-block h-[6px] w-[6px] bg-muted"
            }
            aria-hidden
          />
          {label}
        </span>
        <button
          type="button"
          onClick={() => setFollow((value) => !value)}
          className="border border-line px-2 py-[2px] tracking-widest hover:bg-surface"
        >
          {follow ? "following" : "paused"}
        </button>
      </div>

      <div className="mt-3 max-h-[70vh] overflow-y-auto border border-line p-4">
        {rows.length === 0 ? (
          <p className="text-muted">no events recorded.</p>
        ) : (
          <ol className="space-y-1">
            {rows.map((event) => (
              <li key={event.id} className="grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-0.5 sm:grid-cols-[5.5rem_11rem_1fr]">
                <span className="text-muted">{clock(event.occurred_at)}</span>
                <span className={LEVEL_COLOR[event.level] ?? "text-bone"}>
                  {event.event_type}
                </span>
                <span className="text-muted">
                  {event.message}
                  {event.replayed ? null : <span className="ml-2 text-amber">new</span>}
                </span>
              </li>
            ))}
          </ol>
        )}
        <div ref={bottom} />
      </div>
    </div>
  );
}
