"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import LiveDock from "@/components/LiveDock";
import { Mark } from "@/components/Mark";

/**
 * One bar, three groups, and nothing else competing for the eye.
 *
 * The previous version put eleven lowercase research routes, three solid
 * buttons and an icon into a single wrapping flex row. On a phone that wrapped
 * into four ragged lines with no hierarchy between them, and on a desktop it
 * was eleven 10px uppercase words in `text-muted` — present, but not readable.
 *
 * The routes have not changed. What changed is that they are now grouped by
 * what a reader is actually looking for — what the system is doing right now,
 * what it has concluded, and what it is made of — and each one carries a line
 * saying what is on the page. Below `lg` the same groups become a panel behind
 * one button, so the bar itself is never more than the mark and that button.
 */

type Item = { href: string; label: string; blurb: string };
type Group = { key: string; label: string; items: Item[] };

const GROUPS: Group[] = [
  {
    key: "live",
    label: "live",
    items: [
      {
        href: "/terminal",
        label: "terminal",
        blurb: "every cycle as it lands, one line each",
      },
      {
        href: "/observe",
        label: "observe",
        blurb: "anomalies the detectors flagged, with the measurement behind them",
      },
      {
        href: "/data",
        label: "data",
        blurb: "the tokens under measurement, and which feed found them",
      },
      {
        href: "/pairings",
        label: "pairings",
        blurb: "what each pool is priced in, and the cohort quoted in tokenised shares",
      },
      {
        href: "/watchlist",
        label: "watchlist",
        blurb: "tokens named by hand, the claims about them, and the measurements beside them",
      },
    ],
  },
  {
    key: "research",
    label: "research",
    items: [
      {
        href: "/thesis",
        label: "theses",
        blurb: "arguments posed before the data existed, and where each one stops being testable",
      },
      {
        href: "/hypotheses",
        label: "hypotheses",
        blurb: "questions posed with the rule that would kill them attached",
      },
      {
        href: "/experiments",
        label: "experiments",
        blurb: "each question run against its own dataset, hashed and re-runnable",
      },
      {
        href: "/findings",
        label: "findings",
        blurb: "the verdicts, rejected and inconclusive ones included",
      },
      {
        href: "/patterns",
        label: "patterns",
        blurb: "the few shapes that have survived repeated testing",
      },
      {
        href: "/research",
        label: "method",
        blurb: "how a question becomes a result, and the work it borrows from",
      },
    ],
  },
  {
    key: "system",
    label: "system",
    items: [
      {
        href: "/memory",
        label: "memory",
        blurb: "what was kept, and what it gets retrieved for",
      },
      {
        href: "/agents",
        label: "agents",
        blurb: "the roles that divide up a single cycle",
      },
      {
        href: "/lore",
        label: "lore",
        blurb: "the character, and the rules it is not allowed to break",
      },
      {
        href: "/roadmap",
        label: "roadmap",
        blurb: "what runs, what is waiting on data, and what will never be built",
      },
    ],
  },
];

const PRIMARY: [string, string][] = [
  ["/about", "about"],
  ["/docs", "docs"],
];

export default function Nav({ beating }: { beating: boolean }) {
  const pathname = usePathname() ?? "/";
  const [open, setOpen] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const bar = useRef<HTMLElement>(null);

  // Every route change closes everything: a panel left hanging over the next
  // page is the most common way a nav like this feels broken.
  useEffect(() => {
    setOpen(null);
    setDrawer(false);
  }, [pathname]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(null);
        setDrawer(false);
      }
    }
    function onClick(event: MouseEvent) {
      if (bar.current && !bar.current.contains(event.target as Node)) setOpen(null);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, []);

  const isCurrent = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const groupIsCurrent = (group: Group) => group.items.some((item) => isCurrent(item.href));

  return (
    <header
      ref={bar}
      className="sticky top-0 z-50 border-b border-line bg-void/90 backdrop-blur-md"
    >
      <nav className="flex h-14 items-center gap-2 px-4 sm:px-6">
        <Link
          href="/"
          className="mr-2 flex shrink-0 items-center gap-2.5 text-bone transition-colors hover:text-magenta"
        >
          <Mark size={20} title="GODGOD" />
          <span className="font-display text-[13px] tracking-[0.2em]">GODGOD</span>
        </Link>

        {/* Desktop: three triggers instead of eleven words. */}
        <div className="hidden lg:flex lg:items-center lg:gap-1">
          {GROUPS.map((group) => {
            const expanded = open === group.key;
            return (
              <div key={group.key} className="relative">
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : group.key)}
                  className={`flex items-center gap-1.5 px-3 py-2 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                    expanded || groupIsCurrent(group)
                      ? "text-bone"
                      : "text-grey hover:text-bone"
                  }`}
                >
                  {group.label}
                  <span
                    aria-hidden
                    className={`text-[8px] transition-transform ${expanded ? "rotate-180" : ""}`}
                  >
                    ▾
                  </span>
                </button>

                {/* Rendered always, hidden with CSS. Mounting the panel only
                    while it is open left twelve of the site's fifteen routes
                    out of the served HTML entirely: an audit crawling the
                    homepage found `/about`, `/docs`, `/token` and nothing
                    else, and concluded the site was a thin landing page with
                    no deeper routes. It was not wrong about what it could
                    see. A link a crawler cannot reach is a link that does not
                    exist to anything but a mouse. */}
                <div
                  aria-hidden={!expanded}
                  className={`absolute left-0 top-full w-[22rem] border border-line bg-void p-1 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.9)] ${
                    expanded ? "" : "pointer-events-none invisible opacity-0"
                  }`}
                >
                  {group.items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      tabIndex={expanded ? undefined : -1}
                      className={`block border-l-2 px-3 py-2.5 transition-colors hover:bg-surface ${
                        isCurrent(item.href)
                          ? "border-magenta bg-surface"
                          : "border-transparent"
                      }`}
                    >
                      <span className="text-[11px] uppercase tracking-[0.16em] text-bone">
                        {item.label}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                        {item.blurb}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-1">
          <div className="hidden items-center gap-1 sm:flex">
            {PRIMARY.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className={`px-3 py-2 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                  isCurrent(href) ? "text-bone" : "text-grey hover:text-bone"
                }`}
              >
                {label}
              </Link>
            ))}
            <Link
              href="/token"
              className="ml-1 border border-bone px-3.5 py-[7px] font-display text-[10px] uppercase tracking-widest text-bone transition-colors hover:border-magenta hover:bg-magenta hover:text-void"
            >
              token
            </Link>
          </div>

          <LiveDock beating={beating} />

          <button
            type="button"
            aria-label={drawer ? "Close menu" : "Open menu"}
            aria-expanded={drawer}
            onClick={() => setDrawer(!drawer)}
            className="-mr-1 p-2.5 text-bone lg:hidden"
          >
            <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
              {drawer ? (
                <path
                  d="M4 4l12 12M16 4L4 16"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  fill="none"
                />
              ) : (
                <path
                  d="M2 5h16M2 10h16M2 15h16"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  fill="none"
                />
              )}
            </svg>
          </button>
        </div>
      </nav>

      {/* Mobile: the same three groups, stacked on purpose rather than by
          accident of wrapping. */}
      {drawer ? (
        <div className="max-h-[calc(100vh-3.5rem)] overflow-y-auto border-t border-line bg-void px-4 pb-6 sm:px-6 lg:hidden">
          {GROUPS.map((group) => (
            <div key={group.key} className="pt-5">
              <div className="label">{group.label}</div>
              <div className="mt-2">
                {group.items.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`block border-l-2 py-2.5 pl-3 ${
                      isCurrent(item.href) ? "border-magenta" : "border-line"
                    }`}
                  >
                    <span className="text-[12px] uppercase tracking-[0.16em] text-bone">
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                      {item.blurb}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ))}

          <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-line pt-5">
            {PRIMARY.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className="border border-line px-3.5 py-2 text-[11px] uppercase tracking-[0.16em] text-bone"
              >
                {label}
              </Link>
            ))}
            <Link
              href="/token"
              className="border border-bone bg-bone px-3.5 py-2 font-display text-[10px] uppercase tracking-widest text-void"
            >
              token
            </Link>
          </div>
        </div>
      ) : null}
    </header>
  );
}
