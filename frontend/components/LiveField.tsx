"use client";

import { useEffect, useRef, useState } from "react";

import FieldSphere, { type Shock } from "@/components/FieldSphere";
import { API_URL } from "@/lib/api";
import type { StreamEvent, SystemStateName } from "@/lib/types";

/**
 * The field, reacting to the system as it works.
 *
 * The sphere was already bound to real values, but it read them once, when the
 * page rendered. Between two page loads it described a moment that had passed:
 * a system that had run four cycles since the tab was opened still drew the
 * state it was in before the first one.
 *
 * It now subscribes to the same event stream the terminal reads. Every row the
 * system writes sends a front across the shell, and that front is the only
 * coupling between the points — an honest one. They are not attracting each
 * other; they are all reading the same event.
 *
 * Nothing here invents activity. Replayed history is ignored, because it did
 * not just happen. A quiet system draws a still sphere, which is what a quiet
 * system should look like.
 */

const LEVEL_STRENGTH: Record<string, number> = {
  ERROR: 1,
  WARN: 0.8,
};

/**
 * A point on the unit sphere, derived from the event id.
 *
 * Deterministic on purpose: the same row always lands in the same place. A
 * front whose origin moved between reloads would be decoration wearing the
 * costume of data.
 */
export function directionFor(id: string): [number, number, number] {
  let hash = 2166136261;
  for (let index = 0; index < id.length; index += 1) {
    hash ^= id.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  const y = (((hash >>> 8) & 0xffff) / 0xffff) * 2 - 1;
  const theta = (((hash >>> 24) & 0xff) / 255) * Math.PI * 2;
  const radius = Math.sqrt(Math.max(0, 1 - y * y));
  return [Math.cos(theta) * radius, y, Math.sin(theta) * radius];
}

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  size?: number;
};

export default function LiveField({ state, activity, novelty, confidence, size }: Props) {
  const [shock, setShock] = useState<Shock | null>(null);
  const [received, setReceived] = useState(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    if (typeof window === "undefined" || typeof EventSource === "undefined") return;

    const source = new EventSource(`${API_URL}/api/live/stream`);

    source.addEventListener("log", (message) => {
      const event = JSON.parse((message as MessageEvent).data) as StreamEvent;
      // Replay is history. Presenting it as something happening now is what the
      // stream contract forbids, and it would be worse here than in the
      // terminal: a moving sphere reads as a working system.
      if (event.replayed || !alive.current) return;
      setReceived((count) => count + 1);
      setShock({
        at: performance.now(),
        dir: directionFor(event.id),
        strength: LEVEL_STRENGTH[event.level] ?? 0.55,
      });
    });

    return () => {
      alive.current = false;
      source.close();
    };
  }, []);

  return (
    <div className="flex flex-col items-center">
      <FieldSphere
        state={state}
        activity={activity}
        novelty={novelty}
        confidence={confidence}
        size={size}
        shock={shock}
      />
      <p className="mt-3 text-[10px] uppercase tracking-widest text-muted">
        {received === 0
          ? "no row written since you opened this"
          : `${received} row${received === 1 ? "" : "s"} written since you opened this`}
      </p>
    </div>
  );
}
