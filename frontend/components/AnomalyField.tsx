"use client";

import { useEffect, useRef } from "react";

import type { SystemStateName } from "@/lib/types";

/**
 * The GODGOD field.
 *
 * Every visual parameter is bound to a real system value:
 *   - ring count and rotation speed   -> activity (events in the last hour)
 *   - radial distortion               -> novelty of the current observation
 *   - core radius                     -> confidence in the current hypothesis
 *   - colour                          -> the state machine
 * Nothing here is random. A frozen system draws a frozen field.
 */

const STATE_COLOR: Record<SystemStateName, string> = {
  IDLE: "#6f6f78",
  OBSERVING: "#ededea",
  ANALYZING: "#7b5cff",
  HYPOTHESIZING: "#7b5cff",
  TESTING: "#c9f227",
  REJECTED: "#7b5cff",
  SUPPORTED: "#c9f227",
  LEARNING: "#ededea",
};

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  size?: number;
};

export default function AnomalyField({ state, activity, novelty, confidence, size = 520 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 2) : 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const color = STATE_COLOR[state] ?? "#6f6f78";
    const rings = 14 + Math.round(activity * 22);
    const distortion = 0.06 + (novelty ?? 0) * 0.34;
    const core = 0.08 + (confidence ?? 0) * 0.16;
    const speed = reduceMotion ? 0 : 0.05 + activity * 0.45;

    let frame = 0;
    let raf = 0;

    const draw = () => {
      const cx = size / 2;
      const cy = size / 2;
      const max = size * 0.44;

      ctx.clearRect(0, 0, size, size);

      for (let r = 0; r < rings; r += 1) {
        const t = r / rings;
        const radius = max * (core + (1 - core) * t);
        const phase = frame * speed * (0.2 + t) * 0.02;

        ctx.beginPath();
        for (let a = 0; a <= 360; a += 2) {
          const rad = (a * Math.PI) / 180;
          const wobble =
            Math.sin(rad * 3 + phase + r * 0.6) * 0.5 +
            Math.sin(rad * 7 - phase * 1.3 + r * 0.2) * 0.3 +
            Math.sin(rad * 11 + phase * 0.7) * 0.2;
          const rr = radius * (1 + wobble * distortion * t);
          const x = cx + Math.cos(rad) * rr;
          const y = cy + Math.sin(rad) * rr;
          if (a === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.06 + (1 - t) * 0.3;
        ctx.lineWidth = t < 0.15 ? 1.2 : 0.6;
        ctx.stroke();
      }

      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, max * core * 0.5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.9;
      ctx.fill();
      ctx.globalAlpha = 1;

      if (speed > 0) {
        frame += 1;
        raf = requestAnimationFrame(draw);
      }
    };

    draw();
    return () => cancelAnimationFrame(raf);
  }, [state, activity, novelty, confidence, size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      aria-label={`GODGOD field. state ${state}, activity ${activity.toFixed(2)}`}
      role="img"
    />
  );
}
