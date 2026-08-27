"use client";

import { useState } from "react";

import FieldSphere from "@/components/FieldSphere";
import type { SystemStateName } from "@/lib/types";

/**
 * The sphere at the top of the page.
 *
 * Rendered at the video's native 16:9 and at the full width of the column. An
 * earlier version cropped it to a square, which looked tidy and cut about five
 * hundred pixels off each side — by the end of the loop the sphere and its
 * cabling span almost the entire frame, so a square crop removes the half of
 * the composition that gives it scale.
 *
 * Falls back to the live WebGL field if the video will not decode. The two are
 * not the same thing: the video is a fixed loop and cannot represent state, so
 * it is `aria-hidden` and the numbers underneath stay the evidence. The field
 * *is* bound to activity, novelty and confidence.
 */

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
};

export default function Hero({ state, activity, novelty, confidence }: Props) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="flex justify-center">
        <FieldSphere
          state={state}
          activity={activity}
          novelty={novelty}
          confidence={confidence}
          size={520}
        />
      </div>
    );
  }

  return (
    <div className="relative w-full">
      <video
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        poster="/sphere-poster.jpg"
        aria-hidden
        className="aspect-video w-full object-cover"
        onError={() => setFailed(true)}
      >
        {/* VP9 first: same picture, ~20% lighter. */}
        <source src="/sphere.webm" type="video/webm" />
        <source src="/sphere.mp4" type="video/mp4" />
      </video>

      <span className="sr-only">
        {`GODGOD field. state ${state}, activity ${activity.toFixed(2)}`}
      </span>
    </div>
  );
}
