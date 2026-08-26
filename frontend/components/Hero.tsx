"use client";

import { useState } from "react";

import FieldSphere from "@/components/FieldSphere";
import type { SystemStateName } from "@/lib/types";

/**
 * The sphere at the top of the page.
 *
 * Plays the rendered loop, and falls back to the live WebGL field if the video
 * fails for any reason — a codec the browser will not decode, a blocked
 * request, a corrupt file. The fallback is the same component the page used
 * before the video existed, so the failure costs nothing.
 *
 * The two are not the same thing and the page does not pretend otherwise. The
 * video is a fixed loop: it cannot represent state, so it is `aria-hidden` and
 * the real numbers live in the text underneath. The WebGL field *is* bound to
 * activity, novelty and confidence.
 */

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  size?: number;
};

export default function Hero({ state, activity, novelty, confidence, size = 520 }: Props) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <FieldSphere
        state={state}
        activity={activity}
        novelty={novelty}
        confidence={confidence}
        size={size}
      />
    );
  }

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <video
        width={size}
        height={size}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        poster="/sphere-poster.jpg"
        aria-hidden
        className="h-full w-full object-contain"
        onError={() => setFailed(true)}
      >
        {/* VP9 first: same picture, a fifth smaller. */}
        <source src="/sphere.webm" type="video/webm" />
        <source src="/sphere.mp4" type="video/mp4" />
      </video>

      <span className="sr-only">
        {`GODGOD field. state ${state}, activity ${activity.toFixed(2)}`}
      </span>
    </div>
  );
}
