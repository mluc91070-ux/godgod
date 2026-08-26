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

type Connection = "connecting" | "open" | "closed" | "unsupported";

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

    source.addEventListener("open", () => setConnection("open"));

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

    source.onerror = () => {
      if (!closed) setConnection("connecting");
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
              <li key={event.id} className="grid grid-cols-[5.5rem_11rem_1fr] gap-3">
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
