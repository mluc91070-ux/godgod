"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL } from "@/lib/api";
import type { Observation, StreamEvent, TokenInfo } from "@/lib/types";

/**
 * The population under measurement, drawn as a sphere.
 *
 * One mark per token the system has actually measured, one filament between
 * two tokens whose measurements tripped the same detector. The shape is a
 * sphere because every mark sits on it — nothing here is arranged for looks:
 *
 *   longitude  <- a hash of the token address, so a token keeps its place
 *                 across reloads and between visitors
 *   latitude   <- age: the newest arrivals ring the top, the ones that have
 *                 been measured for two weeks ring the bottom
 *   size       <- liquidity, on a log scale, because the range spans five
 *                 orders of magnitude and a linear one draws one dot and dust
 *   shape      <- the sampling frame: a filled mark completed a bonding curve,
 *                 a ring was found by the promotion feed. That distinction
 *                 changes what a result about the token would mean, so it is
 *                 drawn rather than dropped.
 *   brightness <- the novelty of its most recent observation, dimmed by depth
 *   filament   <- a detector that fired on both ends
 *   label      <- the few with the highest novelty, on the near face, carrying
 *                 their own numbers
 *
 * White throughout: depth and novelty are the only things that change a mark's
 * brightness, so a bright point is a real signal rather than a palette choice.
 *
 * A token nobody has measured is not here. A sparse sphere is a quiet market,
 * and the count under it says how many marks are being drawn so an empty
 * picture cannot be mistaken for a broken one.
 */

const MAX_NODES = 420;
/** Past this the surface reads as noise and stops being legible. The count is
 *  displayed, so the cap is visible rather than silently applied. */

const MAX_LABELS = 10;
const SHOCK_MS = 1600;
const TWO_WEEKS_HOURS = 336;

const PROMOTION = "promotion-feed";

type Node = {
  address: string;
  symbol: string;
  /** Unit-sphere coordinates. `y` is the pole axis. */
  x: number;
  y: number;
  z: number;
  size: number;
  filled: boolean;
  novelty: number;
  liquidity: number | null;
  detectors: string[];
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
    const longitude = ((seed & 0xffff) / 0xffff) * Math.PI * 2;

    // Age decides the latitude: a token that arrived this hour rings the top,
    // one measured for a fortnight rings the bottom. An unknown launch time
    // sits on the equator, which is where "we do not know" belongs.
    const hours = token.launch_time
      ? Math.max(0, (Date.now() - Date.parse(token.launch_time)) / 3_600_000)
      : null;
    const aged = hours === null ? 0.5 : Math.min(1, hours / TWO_WEEKS_HOURS);
    // Jitter keeps a crowded band from collapsing into one hard line. It is
    // bounded and derived from the address, so it never moves either.
    const jitter = ((((seed >>> 16) & 0xff) / 0xff) - 0.5) * 0.14;
    const y = Math.max(-0.98, Math.min(0.98, 1 - aged * 2 + jitter));
    const ring = Math.sqrt(Math.max(0, 1 - y * y));

    const observation = latest.get(token.address);
    const payload = (observation?.payload ?? {}) as { detectors_fired?: string[] };

    return {
      address: token.address,
      symbol: token.symbol ?? "—",
      x: Math.cos(longitude) * ring,
      y,
      z: Math.sin(longitude) * ring,
      size: Math.max(1, Math.log10(Math.max(10, token.liquidity_usd ?? 10)) - 1.5),
      filled: token.source !== PROMOTION,
      novelty: observation?.novelty_score ?? 0,
      liquidity: token.liquidity_usd,
      detectors: payload.detectors_fired ?? [],
    };
  });
}

/** Two tokens are joined when the same detector fired on both. That is a real
 *  relation between them and the only one this data supports. */
function link(nodes: Node[]): [number, number][] {
  const byDetector = new Map<string, number[]>();
  nodes.forEach((node, index) => {
    for (const detector of node.detectors) {
      const held = byDetector.get(detector) ?? [];
      held.push(index);
      byDetector.set(detector, held);
    }
  });

  const edges: [number, number][] = [];
  for (const members of byDetector.values()) {
    // Chained rather than fully connected: a detector that fired on forty
    // tokens would otherwise draw eight hundred lines and fill the sphere.
    for (let index = 1; index < members.length && index < 40; index += 1) {
      edges.push([members[index - 1], members[index]]);
    }
  }
  return edges;
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
  height = 480,
}: {
  tokens: TokenInfo[];
  observations: Observation[];
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const shockRef = useRef<{ at: number; index: number } | null>(null);
  const [received, setReceived] = useState(0);

  const nodes = build(tokens, observations);
  const edges = link(nodes);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const edgesRef = useRef(edges);
  edgesRef.current = edges;

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
    let raf = 0;
    let start = 0;

    const draw = (now: number) => {
      if (!start) start = now;
      const seconds = (now - start) / 1000;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = canvas.clientWidth;
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      const radius = Math.min(width, height) * 0.42;
      // One turn every three minutes: slow enough to read a label, fast enough
      // that the far face comes round while someone is still on the page.
      const spin = reduceMotion ? 0.6 : (seconds * Math.PI * 2) / 180;
      const cos = Math.cos(spin);
      const sin = Math.sin(spin);
      const current = nodesRef.current;

      /** Rotate about the pole axis, then project. Depth runs 0 (far) to 1
       *  (near) and is the only thing that dims a mark besides its novelty. */
      const place = (node: Node) => {
        const rx = node.x * cos - node.z * sin;
        const rz = node.x * sin + node.z * cos;
        const depth = (rz + 1) / 2;
        const perspective = 0.84 + depth * 0.2;
        return {
          x: cx + rx * radius * perspective,
          y: cy + node.y * radius * perspective,
          depth,
        };
      };

      const hit = shockRef.current;
      const age = hit ? now - hit.at : Infinity;
      const shock = hit && age < SHOCK_MS ? 1 - age / SHOCK_MS : 0;

      ctx.lineWidth = 0.5;
      for (const [a, b] of edgesRef.current) {
        const from = current[a];
        const to = current[b];
        if (!from || !to) continue;
        const p1 = place(from);
        const p2 = place(to);
        const depth = (p1.depth + p2.depth) / 2;
        const heat = Math.max(from.novelty, to.novelty);
        ctx.strokeStyle = `rgba(242, 242, 242, ${(0.06 + heat * 0.18) * (0.22 + depth * 0.78)})`;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }

      current.forEach((node, index) => {
        const point = place(node);
        const lit = hit && index === hit.index ? shock : 0;
        // Most tokens carry no anomaly — 384 of the 400 drawn, on the day this
        // was tuned. If novelty were the only thing lifting a mark off the
        // background, the sphere would be sixteen points and a black disc, so
        // the floor is set high enough that a quiet token is still a mark.
        const alpha = (0.32 + node.novelty * 0.55) * (0.22 + point.depth * 0.78) + lit * 0.7;
        const size = node.size * (0.7 + point.depth * 0.5) * (1 + lit * 1.4);

        ctx.beginPath();
        ctx.arc(point.x, point.y, size, 0, Math.PI * 2);
        if (node.filled) {
          ctx.fillStyle = `rgba(242, 242, 242, ${Math.min(1, alpha)})`;
          ctx.fill();
        } else {
          // The promotion frame is drawn hollow. Same colour, different mark:
          // the distinction survives without a second hue.
          ctx.lineWidth = 0.9;
          ctx.strokeStyle = `rgba(242, 242, 242, ${Math.min(1, alpha + 0.1)})`;
          ctx.stroke();
          ctx.lineWidth = 0.5;
        }

        // The row that just arrived also sends a ring out from its token, so
        // the event is findable on a crowded surface.
        if (lit > 0) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, size + (1 - lit) * 34, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(242, 242, 242, ${lit * 0.32})`;
          ctx.stroke();
        }
      });

      // Labels last, only on the near face, and only for the few with
      // something to say. Everything drawn here is a number already on the row
      // it names.
      const labelled = [...current]
        .map((node) => ({ node, point: place(node) }))
        .filter((entry) => entry.node.novelty > 0 && entry.point.depth > 0.55)
        .sort((a, b) => b.node.novelty - a.node.novelty)
        .slice(0, MAX_LABELS);

      ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
      for (const { node, point } of labelled) {
        const fade = (point.depth - 0.55) / 0.45;
        ctx.fillStyle = `rgba(242, 242, 242, ${0.35 + fade * 0.55})`;
        ctx.fillText(node.symbol.slice(0, 14), point.x + 7, point.y - 4);
        ctx.fillStyle = `rgba(160, 160, 160, ${0.3 + fade * 0.45})`;
        ctx.fillText(money(node.liquidity), point.x + 7, point.y + 7);
      }

      if (!reduceMotion || age < SHOCK_MS) raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [height]);

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
        <span>newest at the top, two weeks measured at the bottom</span>
        <span className="text-line">·</span>
        <span>lines join tokens that tripped the same detector</span>
        <span className="ml-auto">
          {received === 0 ? "no row since you opened this" : `${received} rows live`}
        </span>
      </div>
    </div>
  );
}
