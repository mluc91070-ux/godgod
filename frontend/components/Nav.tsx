import Link from "next/link";

const ROUTES: [string, string][] = [
  ["/", "index"],
  ["/terminal", "terminal"],
  ["/observe", "observe"],
  ["/memory", "memory"],
  ["/hypotheses", "hypotheses"],
  ["/experiments", "experiments"],
  ["/patterns", "patterns"],
  ["/agents", "agents"],
  ["/data", "data"],
  ["/lore", "lore"],
  ["/token", "token"],
  ["/docs", "docs"],
];

export default function Nav() {
  return (
    <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line px-6 py-4">
      <Link href="/" className="text-[11px] tracking-widest text-bone hover:text-lime">
        GODGOD
      </Link>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {ROUTES.slice(1).map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className="text-[10px] uppercase tracking-widest text-muted hover:text-bone"
          >
            {label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
