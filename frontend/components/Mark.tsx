/**
 * The GODGOD symbol.
 *
 * A circle crossed by four axes: vertical, horizontal, and two diagonals that
 * run past the edge. Drawn rather than shipped as a raster so it stays sharp at
 * every size, inherits the surrounding colour, and costs nothing to load.
 *
 * The horizontal axis is two segments meeting at the centre rather than one
 * line through it — that gap is what stops the mark reading as a plain
 * crosshair, and it is in the charter.
 */

type Props = {
  size?: number;
  className?: string;
  title?: string;
};

export function Mark({ size = 28, className, title }: Props) {
  const s = 100;
  const c = s / 2;
  const r = 38;
  // Diagonals overshoot the circle; the charter draws them running past it.
  const d = r * 1.16 * Math.SQRT1_2;
  // The horizontal segments stop short of the centre on both sides.
  const gap = 3;

  return (
    <svg
      viewBox={`0 0 ${s} ${s}`}
      width={size}
      height={size}
      className={className}
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      fill="none"
      stroke="currentColor"
      strokeWidth={3.2}
      strokeLinecap="round"
    >
      <ellipse cx={c} cy={c} rx={r * 0.86} ry={r} />
      <line x1={c} y1={c - r * 1.12} x2={c} y2={c + r * 1.12} />
      <line x1={c - d} y1={c - d} x2={c + d} y2={c + d} />
      <line x1={c + d} y1={c - d} x2={c - d} y2={c + d} />
      <line x1={c - r * 0.86} y1={c} x2={c - gap} y2={c} />
      <line x1={c + gap} y1={c} x2={c + r * 0.86} y2={c} />
    </svg>
  );
}

/** The mark and the wordmark together, as the charter locks them up. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`flex items-center gap-3 ${className ?? ""}`}>
      <Mark size={22} title="GODGOD" />
      <span className="font-display text-[15px] tracking-[0.18em] text-bone">GODGOD</span>
    </span>
  );
}

export default Mark;
