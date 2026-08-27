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

const PRIMARY: [string, string][] = [
  ["/about", "about"],
  ["/token", "token"],
  ["/docs", "docs"],
];

export default function Nav() {
  return (
    <nav className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-6 py-4">
      <Link
        href="/"
        className="flex items-center gap-2.5 text-bone transition-colors hover:text-magenta"
      >
        <Mark size={20} title="GODGOD" />
        <span className="font-display text-[13px] tracking-[0.2em]">GODGOD</span>
      </Link>

      <div className="flex flex-wrap gap-x-4 gap-y-1">
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

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {PRIMARY.map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className="border border-bone bg-bone px-3.5 py-[7px] font-display text-[10px] uppercase tracking-widest text-void transition-colors hover:border-magenta hover:bg-magenta hover:text-void"
          >
            {label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
