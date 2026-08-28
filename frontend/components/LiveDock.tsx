"use client";

import { useEffect, useState } from "react";

import LiveTerminal from "@/components/LiveTerminal";
import { API_URL } from "@/lib/api";

/**
 * The event log, reachable from anywhere, without leaving the page.
 *
 * `/terminal` already exists and is the place to read history. What it cannot
 * do is let someone watching a hypothesis page see the system work while they
 * read it, and that is the thing worth showing: this is not a site with a
 * database behind it, it is a loop that is running right now.
 *
 * The stream is opened only once the panel is opened. A hidden `EventSource`
 * on every page would hold a connection open per tab for something nobody is
 * looking at, and the server ages each one out and reconnects.
 *
 * The dot pulses only while the collection loop is alive — the same rule as
 * the status strip. An indicator that animates regardless would say "running"
 * about a dead loop, which is the one thing it exists to rule out.
 */
export default function LiveDock({ beating }: { beating: boolean }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={open ? "Close the live log" : "Open the live log"}
        title={beating ? "the loop is running — watch it" : "the collection loop is not running"}
        className={`flex items-center gap-1.5 border px-2.5 py-[7px] text-[10px] uppercase tracking-widest transition-colors ${
          open
            ? "border-magenta text-magenta"
            : "border-line text-grey hover:border-bone hover:text-bone"
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            beating ? "live-dot bg-magenta" : "bg-amber"
          }`}
          aria-hidden
        />
        <span className="hidden sm:inline">live</span>
      </button>

      {open ? (
        <div className="fixed inset-x-0 bottom-0 z-[60] border-t border-line bg-void shadow-[0_-20px_60px_-20px_rgba(0,0,0,0.95)]">
          <div className="flex items-center justify-between border-b border-line px-4 py-2 sm:px-6">
            <span className="text-[10px] uppercase tracking-widest text-muted">
              live log — {beating ? "the loop is running" : "the loop is stopped"}
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-[10px] uppercase tracking-widest text-grey transition-colors hover:text-bone"
            >
              close
            </button>
          </div>

          <div className="max-h-[45vh] overflow-y-auto px-4 py-3 sm:px-6">
            {/* No server-rendered history here: this panel is for what happens
                while you watch. `/terminal` is where the past is read. */}
            <LiveTerminal apiUrl={API_URL} initial={[]} />
          </div>
        </div>
      ) : null}
    </>
  );
}
