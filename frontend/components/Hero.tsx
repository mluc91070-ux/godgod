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
 * What replaces it draws the population itself: one mark per measured token,
 * a filament between two that tripped the same detector. If the tokens cannot
 * be reached the sphere still renders the four state values, which is less to
 * look at but is still true.
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
    return <MarketField tokens={tokens} observations={observations ?? []} />;
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
