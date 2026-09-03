import type { ReactNode } from "react";

/**
 * The two networks under measurement, named and marked.
 *
 * The marks are the networks' own, drawn as inline SVG so they cost no request
 * and stay sharp at any size. They identify which chain a row came from and
 * nothing more — neither organisation runs this system, and the site says so
 * everywhere it says anything.
 *
 * Robinhood Chain leads. That is not a ranking and not alphabetical: it is the
 * chain this system was extended to read, the one the equity-quote frame only
 * ever returns, and the subject of the standing thesis. Solana is the older
 * population and keeps second place.
 *
 * The glyph the *field* draws is still the shape, not the logo — a round mark
 * on the home chain, a square one elsewhere — because that encoding carries a
 * fact a logo cannot: a square mark is never filled, since the filled state
 * means a bonding curve completed and that frame is read from a launchpad
 * covering one chain. Both are shown here so the legend can be read against
 * the cloud above it.
 */

function RobinhoodMark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden focusable="false">
      <path
        d="M84 9C55 14 30 34 20 62c-4 12-6 22-6 29 6-2 16-6 26-12 28-16 42-38 44-70Z"
        fill="#CCFF00"
      />
      <path
        d="M14 91 84 9"
        stroke="#0b0b0b"
        strokeWidth="6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

function SolanaMark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 80" aria-hidden focusable="false">
      <defs>
        <linearGradient id="godgod-solana" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="#9945FF" />
          <stop offset="100%" stopColor="#14F195" />
        </linearGradient>
      </defs>
      <g fill="url(#godgod-solana)">
        {/* Three bars, the middle one slanted the other way. That reversal is
            the whole mark; drawn parallel it reads as a stack of dashes. */}
        <path d="M20 2h80L80 22H0Z" />
        <path d="M0 30h80l20 20H20Z" />
        <path d="M20 58h80L80 78H0Z" />
      </g>
    </svg>
  );
}

const CHAINS: {
  key: string;
  label: string;
  note: string;
  mark: (props: { size?: number }) => ReactNode;
}[] = [
  {
    key: "robinhood",
    label: "robinhood chain",
    note: "square · an execution layer that issues tokenised equities",
    mark: RobinhoodMark,
  },
  {
    key: "solana",
    label: "solana",
    note: "round · holder share readable · bonding curves reported",
    mark: SolanaMark,
  },
];

export function ChainGlyph({ chain, size = 12 }: { chain: string; size?: number }) {
  const square = chain !== "solana";
  // Equal area: a square of side s·√(π)/2 covers the same ink as a circle of
  // diameter s. Without it the two populations are not comparable by eye.
  const side = size * 0.886;
  const inset = (size - side) / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden focusable="false">
      {square ? (
        <rect
          x={inset}
          y={inset}
          width={side}
          height={side}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.3}
        />
      ) : (
        <circle
          cx={size / 2}
          cy={size / 2}
          r={size / 2 - 0.8}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.3}
        />
      )}
    </svg>
  );
}

/**
 * Both chains, with what has actually been measured on each.
 *
 * Both are always listed, including one with nothing on it. That is the point:
 * this system reads two networks, and a chain that has produced no rows on this
 * deployment is a fact worth stating rather than a name to hide. The count is
 * measured; a zero says the count is zero, never that the chain is absent from
 * the design.
 */
export default function ChainMarks({
  counts,
  children,
}: {
  counts: Map<string, number>;
  children?: ReactNode;
}) {
  return (
    <div className="mt-4 flex flex-wrap gap-x-8 gap-y-3">
      {CHAINS.map(({ key, label, note, mark: Mark }) => {
        const measured = counts.get(key) ?? 0;
        return (
          <div key={key} className="flex items-center gap-2">
            <Mark size={16} />
            <span className="font-display text-[11px] uppercase tracking-[0.18em] text-bone">
              {label}
            </span>
            <span className={`text-[10px] ${measured > 0 ? "text-muted" : "text-grey"}`}>
              {measured > 0 ? `${measured} drawn` : "none on this deployment yet"}
            </span>
            <span className="hidden text-[10px] text-grey lg:inline">{note}</span>
          </div>
        );
      })}
      {children}
    </div>
  );
}
