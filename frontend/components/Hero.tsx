import LiveField from "@/components/LiveField";
import type { SystemStateName } from "@/lib/types";

/**
 * The field at the top of the page.
 *
 * This used to be a video. The video looked better than the field did and it
 * was the wrong thing on this site: a fixed loop cannot represent state, so it
 * was `aria-hidden` and the numbers underneath had to carry every claim. It
 * animated at the same speed whether the system had run four cycles that hour
 * or had been dead since Tuesday, which on a page whose whole argument is
 * "every visual parameter is bound to a real value" is the one thing it could
 * not be allowed to do.
 *
 * What replaces it was already in the repository and never visible: 24,000
 * points on a Fibonacci sphere, rotation bound to activity, surface to
 * novelty, core radius to confidence, colour to the state machine — and now a
 * front crossing the shell for every row the system writes.
 *
 * It also removes 1.8MB of video from the page.
 */

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
};

export default function Hero({ state, activity, novelty, confidence }: Props) {
  return (
    <div className="flex justify-center">
      <LiveField
        state={state}
        activity={activity}
        novelty={novelty}
        confidence={confidence}
        size={520}
      />
    </div>
  );
}
