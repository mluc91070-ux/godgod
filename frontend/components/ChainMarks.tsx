import type { ReactNode } from "react";

/**
 * The two networks under measurement, drawn in the field's own language.
 *
 * These are marks, not logos. Pasting Solana's or Robinhood's artwork onto a
 * research page would be borrowing two organisations' identity for a system
 * neither of them runs, and it would say nothing a reader needs. What a reader
 * needs is to be able to look at the cloud above and know which marks are which
 * chain — so the badge here is the *same* glyph the field draws: a round mark
 * for the home chain, a square one for anything else.
 *
 * That encoding is not decorative. A square mark is never filled, because the
 * filled state means a bonding curve completed and the migration frame is read
 * from a launchpad that covers one chain. The shape and the fill are two
 * independent channels because the two facts are independent.
 *
 * Equal area, not equal width: a square drawn at the circle's diameter reads as
 * half again bigger at the same count, and a legend that exaggerates one
 * population over the other is a chart lying quietly.
 */

const CHAINS: { key: string; label: string; note: string }[] = [
  {
    key: "solana",
    label: "solana",
    note: "round · holder share readable · bonding curves reported",
  },
  {
    key: "robinhood",
    label: "robinhood chain",
    note: "square · an execution layer that issues tokenised equities",
  },
];

export function ChainGlyph({ chain, size = 14 }: { chain: string; size?: number }) {
  const square = chain !== "solana";
  // Equal area: a square of side s·√(π)/2 covers the same ink as a circle of
  // diameter s. Without it the two populations are not comparable by eye.
  const side = size * 0.886;
  const inset = (size - side) / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      {square ? (
        <rect
          x={inset}
          y={inset}
          width={side}
          height={side}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.4}
        />
      ) : (
        <circle
          cx={size / 2}
          cy={size / 2}
          r={size / 2 - 0.9}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.4}
        />
      )}
    </svg>
  );
}

/**
 * Both chains, named, with what has actually been measured on each.
 *
 * Both are always listed, including one with nothing on it. That is the point:
 * this system reads two networks, and a chain that has produced no rows on this
 * deployment is a fact worth stating rather than a name to hide. The count is
 * measured; the sentence beside a zero says the count is zero, never that the
 * chain is absent from the design.
 */
export default function ChainMarks({
  counts,
  children,
}: {
  counts: Map<string, number>;
  children?: ReactNode;
}) {
  return (
    <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
      {CHAINS.map(({ key, label, note }) => {
        const measured = counts.get(key) ?? 0;
        return (
          <div key={key} className="flex items-baseline gap-2">
            <span className={measured > 0 ? "text-bone" : "text-grey"}>
              <ChainGlyph chain={key} />
            </span>
            <span className="font-display text-[11px] uppercase tracking-[0.2em] text-bone">
              {label}
            </span>
            <span className={`text-[10px] ${measured > 0 ? "text-muted" : "text-grey"}`}>
              {measured > 0 ? `${measured} drawn` : "none on this deployment yet"}
            </span>
            <span className="hidden text-[10px] text-grey sm:inline">{note}</span>
          </div>
        );
      })}
      {children}
    </div>
  );
}
