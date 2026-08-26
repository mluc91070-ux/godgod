"use client";

import { useEffect, useRef, useState } from "react";

import FieldSphere from "@/components/FieldSphere";
import type { SystemStateName } from "@/lib/types";

/**
 * The sphere at the top of the page.
 *
 * Plays `public/sphere.mp4` when that file exists, and falls back to the live
 * WebGL field when it does not. The probe is a HEAD request rather than a
 * build-time check so dropping the video in and redeploying is the whole
 * operation — no code change, no flag.
 *
 * The two are not equivalent and the page says so. The rendered video is a
 * fixed loop; the WebGL field is drawn from the system's current activity,
 * novelty and confidence. Whichever is showing, the numbers underneath are the
 * real ones — the visual is never the evidence.
 */

const VIDEO = "/sphere.mp4";

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  size?: number;
};

export default function Hero({ state, activity, novelty, confidence, size = 520 }: Props) {
  const [hasVideo, setHasVideo] = useState<boolean | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(VIDEO, { method: "HEAD" })
      .then((response) => {
        if (cancelled) return;
        const type = response.headers.get("content-type") ?? "";
        setHasVideo(response.ok && type.startsWith("video"));
      })
      .catch(() => {
        if (!cancelled) setHasVideo(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Until the probe answers, draw the field: it needs no network and is the
  // honest default. A spinner here would be a blank space that says nothing.
  if (hasVideo !== true) {
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
        ref={videoRef}
        src={VIDEO}
        width={size}
        height={size}
        autoPlay
        muted
        loop
        playsInline
        // A rendered loop cannot represent live state, so it is decoration and
        // is marked as such for anyone not looking at it.
        aria-hidden
        className="h-full w-full object-contain"
        onError={() => setHasVideo(false)}
      />
      <span className="sr-only">
        {`GODGOD field. state ${state}, activity ${activity.toFixed(2)}`}
      </span>
    </div>
  );
}
