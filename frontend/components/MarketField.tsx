"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL } from "@/lib/api";
import type { Observation, StreamEvent, TokenInfo } from "@/lib/types";

/**
 * The population under measurement, drawn as a field.
 *
 * One mark per token the system has actually measured, one filament between
 * two tokens whose measurements tripped the same detector. Nothing here is
 * arranged for looks:
 *
 *   position   <- a hash of the token address, so a token keeps its place
 *                 across reloads and between visitors
 *   radius     <- how recently it was launched: new arrivals land at the edge
 *   size       <- liquidity, on a log scale, because the range spans five
 *                 orders of magnitude and a linear one draws one dot and dust
 *   colour     <- the sampling frame that found it, the one distinction that
 *                 changes what a result about it would mean
 *   brightness <- the novelty of its most recent observation
 *   filament   <- a detector that fired on both ends
 *   label      <- the few with the highest novelty, carrying their own numbers
 *
 * A token nobody has measured is not here. A quiet field is a quiet market,
 * and the count under it says how many marks are being drawn so a sparse
 * picture cannot be mistaken for a broken one.
 */

const MAX_NODES = 420;
/** Past this the field reads as noise and stops being legible. The count is
 *  displayed, so the cap is visible rather than silently applied. */

const MAX_LABELS = 14;
const SHOCK_MS = 1500;

const FRAME_COLOR: Record<string, string> = {
  "promotion-feed": "255, 44, 240",
  "launchpad-migration": "255, 106, 0",
};
const UNRECORDED = "160, 160, 160";

type Node = {
  address: string;
  symbol: string;
  x: number;
  y: number;
  size: number;
  color: string;
  novelty: number;
  liquidity: number | null;
  detectors: string[];
  summary: string | null;
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
    const angle = ((seed & 0xffff) / 0xffff) * Math.PI * 2;
    // Age decides the radius: a token measured for days sits in the body of
    // the field, one that arrived this hour sits on its edge.
    const hours = token.launch_time
      ? Math.max(0, (Date.now() - Date.parse(token.launch_time)) / 3_600_000)
      : null;
    const settled = hours === null ? 0.6 : 1 - Math.min(1, hours / 336);
    const jitter = (((seed >>> 16) & 0xff) / 0xff) * 0.18;
    const radius = 0.28 + settled * 0.6 + jitter;

    const observation = latest.get(token.address);
    const payload = (observation?.payload ?? {}) as { detectors_fired?: string[] };

    return {
      address: token.address,
      symbol: token.symbol ?? "—",
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius * 0.62,
      size: Math.max(1, Math.log10(Math.max(10, token.liquidity_usd ?? 10)) - 1.4),
      color: FRAME_COLOR[token.source ?? ""] ?? UNRECORDED,
      novelty: observation?.novelty_score ?? 0,
      liquidity: token.liquidity_usd,
      detectors: payload.detectors_fired ?? [],
      summary: observation?.summary ?? null,
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
    // tokens would otherwise draw eight hundred lines and hide the field.
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
  height = 460,
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
      const scale = Math.min(width, height * 1.7) * 0.46;
      const drift = reduceMotion ? 0 : seconds * 0.035;
      const current = nodesRef.current;

      const place = (node: Node, index: number) => {
        // A slow shear rather than a spin: the field breathes without any mark
        // leaving the place its address put it.
        const wobble = reduceMotion ? 0 : Math.sin(drift * 2 + index * 0.7) * 0.012;
        return {
          x: cx + (node.x + wobble) * scale * Math.cos(drift * 0.4),
          y: cy + (node.y + wobble * 0.6) * scale,
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
        const p1 = place(from, a);
        const p2 = place(to, b);
        const heat = Math.max(from.novelty, to.novelty);
        ctx.strokeStyle = `rgba(${from.color}, ${0.05 + heat * 0.22})`;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }

      current.forEach((node, index) => {
        const point = place(node, index);
        const lit = hit && index === hit.index ? shock : 0;
        const alpha = 0.25 + node.novelty * 0.55 + lit * 0.6;
        ctx.fillStyle = `rgba(${node.color}, ${Math.min(1, alpha)})`;
        ctx.beginPath();
        ctx.arc(point.x, point.y, node.size * (1 + lit * 1.6), 0, Math.PI * 2);
        ctx.fill();
      });

      // Labels last, and only the few with something to say. Everything drawn
      // here is a number already on the row it names.
      const labelled = [...current]
        .map((node, index) => ({ node, index }))
        .filter((entry) => entry.node.novelty > 0)
        .sort((a, b) => b.node.novelty - a.node.novelty)
        .slice(0, MAX_LABELS);

      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
      for (const { node, index } of labelled) {
        const point = place(node, index);
        ctx.fillStyle = `rgba(${node.color}, 0.9)`;
        ctx.fillText(node.symbol.slice(0, 14), point.x + 6, point.y - 4);
        ctx.fillStyle = "rgba(160, 160, 160, 0.75)";
        ctx.fillText(money(node.liquidity), point.x + 6, point.y + 7);
      }

      if (!reduceMotion || age < SHOCK_MS) raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [height]);

  const promoted = nodes.filter((node) => node.color === FRAME_COLOR["promotion-feed"]).length;
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
          <span style={{ color: "#ff6a00" }}>{nodes.length - promoted}</span> migrated
        </span>
        <span className="text-line">·</span>
        <span>
          <span style={{ color: "#ff2cf0" }}>{promoted}</span> promoted
        </span>
        <span className="text-line">·</span>
        <span>
          <span className="text-bone">{flagged}</span> flagged
        </span>
        <span className="text-line">·</span>
        <span>lines join tokens that tripped the same detector</span>
        <span className="ml-auto">
          {received === 0 ? "no row since you opened this" : `${received} rows live`}
        </span>
      </div>
    </div>
  );
}
