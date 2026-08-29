"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL } from "@/lib/api";
import type { Observation, StreamEvent, TokenInfo } from "@/lib/types";

/**
 * The population under measurement, drawn as a cloud around a core.
 *
 * One sphere per token the system has actually measured. There are no lines:
 * the previous version joined tokens that tripped the same detector, and with
 * four detectors firing across four hundred tokens that was a cage, not a
 * relation anyone could read. What is left is the population itself.
 *
 *   direction  <- a hash of the token address, spread evenly over the sphere,
 *                 so a token keeps its place across reloads and between
 *                 visitors and no band collapses into a ring
 *   distance   <- age, on a log scale. The core is where a token enters; it
 *                 drifts outward as it is measured and reaches the shell at a
 *                 day. An unknown launch time sits at mid-depth, which is
 *                 where "we do not know" belongs.
 *   size       <- liquidity, on a log scale, because the range spans five
 *                 orders of magnitude and a linear one draws one dot and dust
 *   shape      <- the sampling frame: a filled sphere completed a bonding
 *                 curve, a ring was found by the promotion feed. That
 *                 distinction changes what a result about the token would
 *                 mean, so it is drawn rather than dropped.
 *   brightness <- the novelty of its most recent observation, dimmed by depth
 *   pulse      <- novelty again: a token with no anomaly does not move at all,
 *                 so motion in the cloud is signal rather than screensaver
 *   rotation   <- activity. A dead loop turns at the floor rate; a working one
 *                 turns faster. It is never zero, or a still image would be
 *                 indistinguishable from a broken canvas.
 *   core       <- the white point at the centre. Its halo is confidence, and
 *                 when confidence is unmeasured there is no halo.
 *
 * White throughout: depth, novelty and the core are the only things that change
 * brightness, so a bright point is a real signal rather than a palette choice.
 *
 * A token nobody has measured is not here. A sparse cloud is a quiet market,
 * and the count under it says how many spheres are being drawn so an empty
 * picture cannot be mistaken for a broken one.
 */

const MAX_NODES = 420;
/** Past this the cloud reads as noise and stops being legible. The count is
 *  displayed, so the cap is visible rather than silently applied. */

const MAX_LABELS = 10;
const SHOCK_MS = 1600;
/** Age is placed on a log scale between these bounds. Measured on the live
 *  population: 397 of 400 tokens are under a day old, so a linear two-week
 *  scale put every one of them at the same distance and the cloud collapsed to
 *  a thin shell.
 *
 *  A day is the shell because that is the scale this population actually
 *  occupies. A week put the outer edge where only three tokens ever reached
 *  it, and the visible cloud filled 56% of the frame; at a day it fills 88%.
 *  Older tokens pin to the shell — "at least a day" — rather than being
 *  dropped, and the legend says a day so the clamp is stated rather than
 *  hidden. */
const AGE_FLOOR_HOURS = 0.5;
const AGE_SHELL_HOURS = 24;
/** Seconds for one full turn at rest, and at full activity. Forty seconds was
 *  measured as the point where a point crossing the near face is visibly
 *  moving without the cloud reading as a spinning logo. */
const TURN_SECONDS_IDLE = 70;
const TURN_SECONDS_BUSY = 34;
/** The cloud is tipped so the far hemisphere is visible past the near one.
 *  Without it the two project onto each other and the volume reads flat. */
const TILT = 0.34;

/** The canvas fills the viewport height rather than a fixed box. The radius is
 *  `min(width, height)`, and on any desktop the height is the binding side, so
 *  this is the only lever that makes the cloud bigger. The floor keeps it
 *  usable on a short window; the ceiling stops it dwarfing the page on a tall
 *  one. */
const CANVAS_HEIGHT = "clamp(460px, 82vh, 960px)";
/** Marks were sized against a 285px radius. Scaling them with the canvas keeps
 *  400 points from reading as dust once the cloud is twice that. */
const REFERENCE_RADIUS = 285;

const PROMOTION = "promotion-feed";

type Node = {
  address: string;
  symbol: string;
  /** Position in the unit ball. `y` is the pole axis. */
  x: number;
  y: number;
  z: number;
  size: number;
  filled: boolean;
  novelty: number;
  /** Phase of this token's pulse, from its address: two tokens with the same
   *  novelty must not breathe in lockstep, and the offset must not be random
   *  or the cloud would look different on every reload. */
  phase: number;
  liquidity: number | null;
};

/** Deterministic 32-bit hash. The same address always lands in the same place:
 *  a layout that moved between reloads would be decoration, not a map. */
function hash(text: string): number {
  let value = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

/** Age as a fraction of the way from the core to the shell, on a log scale.
 *  Linear was measured drawing 400 tokens at one distance. */
function ageFraction(hours: number): number {
  const low = Math.log10(AGE_FLOOR_HOURS);
  const span = Math.log10(AGE_SHELL_HOURS) - low;
  const value = Math.log10(Math.max(AGE_FLOOR_HOURS, hours));
  return Math.max(0, Math.min(1, (value - low) / span));
}

function build(tokens: TokenInfo[], observations: Observation[]): Node[] {
  const latest = new Map<string, Observation>();
  for (const observation of observations) {
    const key = observation.subject_ref;
    if (!key) continue;
    const held = latest.get(key);
    if (!held || (observation.novelty_score ?? 0) > (held.novelty_score ?? 0)) {
      latest.set(key, observation);
    }
  }

  const measured = tokens.filter((token) => token.liquidity_usd !== null);
  // The most liquid first, so the cap drops the dust rather than the market.
  measured.sort((a, b) => (b.liquidity_usd ?? 0) - (a.liquidity_usd ?? 0));

  return measured.slice(0, MAX_NODES).map((token) => {
    const seed = hash(token.address);
    // Two independent halves of the hash: longitude, and a cosine-uniform
    // latitude. Taking the angle uniformly instead would crowd the poles.
    const longitude = ((seed & 0xffff) / 0xffff) * Math.PI * 2;
    const up = (((seed >>> 16) & 0xffff) / 0xffff) * 2 - 1;
    const ring = Math.sqrt(Math.max(0, 1 - up * up));

    // Age decides the distance from the core: a token that arrived this hour
    // sits near the centre, one a week old sits on the shell.
    const hours = token.launch_time
      ? Math.max(0, (Date.now() - Date.parse(token.launch_time)) / 3_600_000)
      : null;
    const aged = hours === null ? 0.5 : ageFraction(hours);
    // The inner floor keeps the newest arrivals off the core itself, which is
    // a different thing and must stay readable as one.
    const distance = 0.24 + aged * 0.72;

    const observation = latest.get(token.address);

    return {
      address: token.address,
      symbol: token.symbol ?? "—",
      x: Math.cos(longitude) * ring * distance,
      y: up * distance,
      z: Math.sin(longitude) * ring * distance,
      size: Math.max(1.4, (Math.log10(Math.max(10, token.liquidity_usd ?? 10)) - 2.9) * 1.5 + 1.4),
      filled: token.source !== PROMOTION,
      novelty: observation?.novelty_score ?? 0,
      phase: ((seed >>> 8) & 0xff) / 0xff * Math.PI * 2,
      liquidity: token.liquidity_usd,
    };
  });
}

function money(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}k`;
  return `$${value.toFixed(0)}`;
}

export default function MarketField({
  tokens,
  observations,
  activity = 0,
  confidence = null,
  height = CANVAS_HEIGHT,
}: {
  tokens: TokenInfo[];
  observations: Observation[];
  activity?: number;
  confidence?: number | null;
  height?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const shockRef = useRef<{ at: number; index: number } | null>(null);
  const [received, setReceived] = useState(0);

  const nodes = build(tokens, observations);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  // Every row the system writes lights the token it is about, when that token
  // is on screen. Replayed history lights nothing: it did not just happen.
  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") return;
    const source = new EventSource(`${API_URL}/api/live/stream`);
    source.addEventListener("log", (message) => {
      const event = JSON.parse((message as MessageEvent).data) as StreamEvent;
      if (event.replayed) return;
      setReceived((count) => count + 1);
      const index = nodesRef.current.findIndex((node) => node.address === event.ref_id);
      shockRef.current = {
        at: performance.now(),
        index: index >= 0 ? index : hash(event.id) % Math.max(1, nodesRef.current.length),
      };
    });
    return () => source.close();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Activity is a count of what the loop did this cycle. Four is a busy
    // quarter hour; past that the rate is held rather than climbing forever.
    const busy = Math.min(1, activity / 4);
    const turnSeconds = TURN_SECONDS_IDLE - (TURN_SECONDS_IDLE - TURN_SECONDS_BUSY) * busy;

    let raf = 0;
    let start = 0;

    const draw = (now: number) => {
      if (!start) start = now;
      const seconds = (now - start) / 1000;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      // Read the box CSS actually gave us rather than a prop: the height is a
      // viewport clamp, so it changes on resize and on an orientation flip
      // without this component being told.
      const width = canvas.clientWidth;
      const boxHeight = canvas.clientHeight;
      if (canvas.width !== width * dpr || canvas.height !== boxHeight * dpr) {
        canvas.width = width * dpr;
        canvas.height = boxHeight * dpr;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, boxHeight);

      const cx = width / 2;
      const cy = boxHeight / 2;
      // 0.47 rather than half: the outermost tokens sit at distance 0.96, the
      // perspective term adds 4%, and each mark carries a halo. Checked
      // numerically against the live population — nothing clips.
      const radius = Math.min(width, boxHeight) * 0.47;
      const markScale = radius / REFERENCE_RADIUS;
      const spin = reduceMotion ? 0.6 : (seconds * Math.PI * 2) / turnSeconds;
      const cos = Math.cos(spin);
      const sin = Math.sin(spin);
      const tiltCos = Math.cos(TILT);
      const tiltSin = Math.sin(TILT);
      const current = nodesRef.current;

      const hit = shockRef.current;
      const age = hit ? now - hit.at : Infinity;
      const shock = hit && age < SHOCK_MS ? 1 - age / SHOCK_MS : 0;

      /** Spin about the pole, tip toward the viewer, then project. Depth runs
       *  0 (far) to 1 (near) and is what makes the cloud a volume. */
      const place = (node: Node) => {
        // A token with no anomaly has amplitude zero and does not move.
        const pulse = reduceMotion
          ? 1
          : 1 + Math.sin(seconds * 1.1 + node.phase) * 0.07 * node.novelty;
        const px = node.x * pulse;
        const py = node.y * pulse;
        const pz = node.z * pulse;

        const rx = px * cos - pz * sin;
        const rz = px * sin + pz * cos;
        const ry = py * tiltCos - rz * tiltSin;
        const dz = py * tiltSin + rz * tiltCos;

        const depth = (dz + 1) / 2;
        const perspective = 0.82 + depth * 0.22;
        return {
          x: cx + rx * radius * perspective,
          y: cy + ry * radius * perspective,
          depth,
        };
      };

      // Far half first, then the core, then the near half: the core has to be
      // occluded by what is in front of it or the cloud loses its inside.
      const placed = current
        .map((node, index) => ({ node, index, point: place(node) }))
        .sort((a, b) => a.point.depth - b.point.depth);

      const paint = (entry: (typeof placed)[number]) => {
        const { node, index, point } = entry;
        const lit = hit && index === hit.index ? shock : 0;
        // Novelty is sparse — most tokens carry no anomaly — so the floor is
        // set high enough that a quiet token is still a sphere rather than
        // leaving the cloud as a dozen points on a black field.
        const alpha = (0.55 + node.novelty * 0.45) * (0.32 + point.depth * 0.68) + lit * 0.6;
        const size = node.size * markScale * (0.68 + point.depth * 0.55) * (1 + lit * 1.5);

        // A soft halo under each mark: it is what makes a flat disc read as a
        // small sphere, and it costs one extra arc per point.
        ctx.beginPath();
        ctx.arc(point.x, point.y, size * 2.6, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(242, 242, 242, ${Math.min(1, alpha) * 0.1})`;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(point.x, point.y, size, 0, Math.PI * 2);
        if (node.filled) {
          ctx.fillStyle = `rgba(242, 242, 242, ${Math.min(1, alpha)})`;
          ctx.fill();
        } else {
          // The promotion frame is drawn hollow. Same colour, different mark:
          // the distinction survives without a second hue.
          ctx.lineWidth = 1;
          ctx.strokeStyle = `rgba(242, 242, 242, ${Math.min(1, alpha + 0.12)})`;
          ctx.stroke();
        }

        // The row that just arrived also sends a ring out from its token, so
        // the event is findable in a crowded cloud.
        if (lit > 0) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, size + (1 - lit) * 40 * markScale, 0, Math.PI * 2);
          ctx.lineWidth = 1;
          ctx.strokeStyle = `rgba(242, 242, 242, ${lit * 0.3})`;
          ctx.stroke();
        }
      };

      let cursor = 0;
      while (cursor < placed.length && placed[cursor].point.depth < 0.5) {
        paint(placed[cursor]);
        cursor += 1;
      }

      // The core. Confidence is a halo around it; when confidence has not been
      // measured there is no halo, rather than a halo standing for zero.
      if (confidence !== null) {
        const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 0.34);
        halo.addColorStop(0, `rgba(242, 242, 242, ${0.1 + confidence * 0.16})`);
        halo.addColorStop(1, "rgba(242, 242, 242, 0)");
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.34, 0, Math.PI * 2);
        ctx.fillStyle = halo;
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(cx, cy, 5 * markScale, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
      ctx.fill();

      while (cursor < placed.length) {
        paint(placed[cursor]);
        cursor += 1;
      }

      // Labels last, only on the near face, and only for the few with
      // something to say. Everything drawn here is a number already on the row
      // it names.
      const labelled = placed
        .filter((entry) => entry.node.novelty > 0 && entry.point.depth > 0.58)
        .sort((a, b) => b.node.novelty - a.node.novelty)
        .slice(0, MAX_LABELS);

      ctx.font = `${Math.round(10 * Math.min(1.4, markScale))}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`;
      for (const { node, point } of labelled) {
        const fade = (point.depth - 0.58) / 0.42;
        ctx.fillStyle = `rgba(242, 242, 242, ${0.35 + fade * 0.55})`;
        ctx.fillText(node.symbol.slice(0, 14), point.x + 8, point.y - 4);
        ctx.fillStyle = `rgba(160, 160, 160, ${0.3 + fade * 0.45})`;
        ctx.fillText(money(node.liquidity), point.x + 8, point.y + 7);
      }

      if (!reduceMotion || age < SHOCK_MS) raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [activity, confidence]);

  const promoted = nodes.filter((node) => !node.filled).length;
  const flagged = nodes.filter((node) => node.novelty > 0).length;

  return (
    <div className="w-full">
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height }}
        role="img"
        aria-label={`${nodes.length} tokens under measurement, ${flagged} with a recent anomaly`}
      />
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
        <span>
          <span className="text-bone">{nodes.length}</span> tokens drawn
        </span>
        <span className="text-line">·</span>
        <span>
          <span className="text-bone">{nodes.length - promoted}</span> migrated — filled
        </span>
        <span className="text-line">·</span>
        <span>
          <span className="text-bone">{promoted}</span> promoted — hollow
        </span>
        <span className="text-line">·</span>
        <span>
          <span className="text-bone">{flagged}</span> flagged
        </span>
        <span className="text-line">·</span>
        <span>new near the core, a day measured at the shell</span>
        <span className="ml-auto">
          {received === 0 ? "no row since you opened this" : `${received} rows live`}
        </span>
      </div>
    </div>
  );
}
