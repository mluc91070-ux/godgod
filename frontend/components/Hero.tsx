import LiveField from "@/components/LiveField";
import MarketField from "@/components/MarketField";
import type { Observation, SystemStateName, TokenInfo } from "@/lib/types";

/**
 * The field at the top of the page.
 *
 * This used to be a video: a fixed 15-second loop that animated identically
 * whether the system had run four cycles that hour or had been dead since
 * Tuesday. On a page whose argument is that every visual parameter is bound to
 * a real value, that is the one thing it could not be — so it was
 * `aria-hidden` and every claim had to be carried by the numbers underneath.
 * 1.8MB of video went with it.
 *
 * What replaces it is a cloud made of the population itself: one sphere per
 * measured token, placed by its address and its age around a white core. If
 * the tokens cannot be reached the state sphere renders instead — less to look
 * at, still true.
 */

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  tokens?: TokenInfo[];
  observations?: Observation[];
};

export default function Hero({
  state,
  activity,
  novelty,
  confidence,
  tokens,
  observations,
}: Props) {
  if (tokens && tokens.length > 0) {
    // Activity turns the cloud and confidence lights its core, so the two
    // state values that have a visual meaning here still have one.
    return (
      <MarketField
        tokens={tokens}
        observations={observations ?? []}
        activity={activity}
        confidence={confidence}
      />
    );
  }

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
