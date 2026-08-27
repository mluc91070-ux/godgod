import Link from "next/link";

import { Mark } from "@/components/Mark";

/**
 * Two kinds of link, and they are visually separate on purpose.
 *
 * The research routes are where the system's own work lives — a long list a
 * reader scans. `about`, `token` and `docs` are what a first-time visitor
 * actually needs: what this is, what the token is, and how it works. Those sit
 * in solid buttons at the end of the bar, because a first-time visitor should
 * not have to find them inside a list of fourteen lowercase words.
 */

const RESEARCH: [string, string][] = [
  ["/terminal", "terminal"],
  ["/observe", "observe"],
  ["/memory", "memory"],
  ["/hypotheses", "hypotheses"],
  ["/experiments", "experiments"],
  ["/findings", "findings"],
  ["/patterns", "patterns"],
  ["/research", "research"],
  ["/agents", "agents"],
  ["/data", "data"],
  ["/lore", "lore"],
];

export const X_URL = "https://x.com/godgodai";

const PRIMARY: [string, string][] = [
  ["/about", "about"],
  ["/token", "token"],
  ["/docs", "docs"],
];

export default function Nav() {
  return (
    <nav className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-4 py-4 sm:px-6">
      <Link
        href="/"
        className="flex items-center gap-2.5 text-bone transition-colors hover:text-magenta"
      >
        <Mark size={20} title="GODGOD" />
        <span className="font-display text-[13px] tracking-[0.2em]">GODGOD</span>
      </Link>

      <div className="order-3 flex min-w-0 flex-wrap gap-x-4 gap-y-1 sm:order-none">
        {RESEARCH.map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className="text-[10px] uppercase tracking-widest text-muted transition-colors hover:text-bone"
          >
            {label}
          </Link>
        ))}
      </div>

      <div className="order-2 ml-auto flex min-w-0 flex-wrap items-center gap-2 sm:order-none">
        {PRIMARY.map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className="border border-bone bg-bone px-3.5 py-[7px] font-display text-[10px] uppercase tracking-widest text-void transition-colors hover:border-magenta hover:bg-magenta hover:text-void"
          >
            {label}
          </Link>
        ))}
        <a
          href={X_URL}
          target="_blank"
          rel="noreferrer noopener"
          aria-label="GODGOD on X"
          className="border border-line px-3 py-[9px] text-grey transition-colors hover:border-bone hover:text-bone"
        >
          <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden>
            <path d="M18.9 2H22l-7.1 8.1L23.2 22h-6.6l-5.2-6.8L5.5 22H2.4l7.6-8.7L1.2 2h6.8l4.7 6.2L18.9 2Zm-1.1 18.1h1.7L7.3 3.8H5.5l12.3 16.3Z" />
          </svg>
        </a>
      </div>
    </nav>
  );
}
