/**
 * The GODGOD symbol.
 *
 * Measured off the reference render rather than eyeballed — the proportions
 * below are the ones in the artwork, normalised to a 100-unit box:
 *
 *   circle          r = 39, split by a ±5° gap at top and bottom where the
 *                   vertical passes through
 *   vertical        the full diameter, continuous
 *   horizontal      two spokes, 0.17R to 0.84R — they stay inside the circle
 *   diagonals       four spokes, 0.20R to 1.21R — these punch through it
 *   centre          a small node the spokes stop short of
 *
 * The asymmetry between the horizontal spokes and the diagonals is deliberate
 * and is what stops the mark reading as a wheel.
 *
 * Drawn as SVG so it stays sharp at every size, inherits the surrounding
 * colour, and costs nothing to load. `simplified` drops the detail that turns
 * to mush below ~24px; see scripts/build_brand.py.
 */

const C = 50;
const R = 39;
const GAP_DEG = 5;

function point(angleDeg: number, radius: number): [number, number] {
  const t = (angleDeg * Math.PI) / 180;
  return [C + radius * Math.cos(t), C + radius * Math.sin(t)];
}

/** The circle as two arcs, leaving the vertical a clean path through. */
function arc(fromDeg: number, toDeg: number): string {
  const [x1, y1] = point(fromDeg, R);
  const [x2, y2] = point(toDeg, R);
  const large = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

function Spoke({ angle, from, to }: { angle: number; from: number; to: number }) {
  const [x1, y1] = point(angle, from);
  const [x2, y2] = point(angle, to);
  return <line x1={x1} y1={y1} x2={x2} y2={y2} />;
}

type Props = {
  size?: number;
  className?: string;
  title?: string;
  simplified?: boolean;
};

export function Mark({ size = 28, className, title, simplified = false }: Props) {
  const strokeWidth = simplified ? 5 : 3.4;

  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="butt"
    >
      <path d={arc(90 + GAP_DEG, 270 - GAP_DEG)} />
      <path d={arc(270 + GAP_DEG, 90 - GAP_DEG)} />

      <line x1={C} y1={C - R} x2={C} y2={C + R} />

      {[45, 135, 225, 315].map((angle) => (
        <Spoke key={angle} angle={angle} from={R * 0.2} to={R * 1.21} />
      ))}

      {simplified ? null : (
        <>
          <Spoke angle={0} from={R * 0.17} to={R * 0.84} />
          <Spoke angle={180} from={R * 0.17} to={R * 0.84} />
        </>
      )}
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
