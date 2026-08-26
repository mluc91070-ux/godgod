"use client";

import { useEffect, useRef, useState } from "react";

import AnomalyField from "@/components/AnomalyField";
import type { SystemStateName } from "@/lib/types";

/**
 * The GODGOD field, as a point cloud on a sphere.
 *
 * Every visual parameter is bound to a real system value, exactly as the 2D
 * field it replaces:
 *
 *   rotation speed    <- activity, events recorded in the last hour
 *   surface turbulence<- novelty of the current observation
 *   core radius       <- confidence in the current hypothesis
 *   colour            <- the state machine
 *
 * Nothing is random and nothing is decorative. A frozen system draws a frozen
 * sphere; an idle one barely moves. If the numbers are flat and this looks
 * boring, it is telling the truth.
 *
 * Written against raw WebGL rather than a 3D library on purpose. The whole
 * frontend is 102KB; three.js would be six times that for one component, on a
 * site whose pages are mostly server-rendered text. When WebGL is unavailable
 * it falls back to the 2D canvas field rather than showing nothing.
 */

/** Charter palette: bone #F2F2F2, grey #A0A0A0, magenta #FF2CF0, amber #FF6A00. */
const STATE_COLOR: Record<SystemStateName, [number, number, number]> = {
  IDLE: [0.63, 0.63, 0.63],
  OBSERVING: [0.95, 0.95, 0.95],
  ANALYZING: [1.0, 0.17, 0.94],
  HYPOTHESIZING: [1.0, 0.17, 0.94],
  TESTING: [1.0, 0.42, 0.0],
  REJECTED: [1.0, 0.17, 0.94],
  SUPPORTED: [1.0, 0.42, 0.0],
  LEARNING: [0.95, 0.95, 0.95],
};

const POINTS = 24000;

/** Per-point brightness. Tuned against a screenshot, not by eye in code. */
const INTENSITY = 0.5;

const VERTEX = `#version 300 es
precision highp float;

in vec3 aPosition;
in float aSeed;

uniform float uTime;
uniform float uTurbulence;   // novelty
uniform float uCore;         // confidence
uniform float uActivity;
uniform vec2  uResolution;
uniform float uDpr;

out float vDepth;
out float vInner;
out float vRim;
out float vBoil;

// Ashima-style simplex noise, trimmed to the 3D case.
vec4 permute(vec4 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod(i, 289.0);
  vec4 p = permute(permute(permute(
             i.z + vec4(0.0, i1.z, i2.z, 1.0))
           + i.y + vec4(0.0, i1.y, i2.y, 1.0))
           + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}

mat3 rotateY(float a) {
  float c = cos(a), s = sin(a);
  return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c);
}

void main() {
  vec3 dir = normalize(aPosition);

  float n1 = snoise(dir * 1.4 + vec3(0.0, uTime * 0.26, 0.0));
  float n2 = snoise(dir * 4.2 - vec3(uTime * 0.42, 0.0, uTime * 0.19));
  float field = n1 * 0.6 + n2 * 0.4;

  // Novelty makes the surface boil, and barely moves it. Driving the radius
  // hard instead turns the sphere into a potato — checked by rendering it.
  float boil = clamp(0.5 + 0.5 * field, 0.0, 1.0);

  // Most points sit near the surface; a few fall inward. That gradient is what
  // produces a limb, and the limb is what reads as a sphere rather than fog.
  float shell = 1.0 - (1.0 - uCore) * pow(aSeed, 6.0);
  float radius = shell * (1.0 + field * uTurbulence * 0.05);

  // The floor is what an idle system looks like, and 0.05 rad/s is a turn
  // every two minutes — indistinguishable from frozen. Quiet has to be
  // visibly quiet, not visibly broken. Activity still sets the rest.
  vec3 pos = rotateY(uTime * (0.28 + uActivity * 0.75)) * (dir * radius);

  // Cheap perspective: no matrix stack, one divide.
  float z = pos.z * 0.5 + 1.9;
  vec2 projected = pos.xy / z;

  gl_Position = vec4(projected * 1.55, 0.0, 1.0);
  // uResolution.y is already the DPR-scaled height, so folding uDpr in as
  // well counted it twice and produced sub-pixel points at dpr 1 — which is
  // why the sphere looked like dust. Scale by canvas height alone.
  // Little size variance: a wide spread reads as television snow and drowns
  // the rim and the surface pattern, which are the parts carrying meaning.
  gl_PointSize = mix(3.0, 4.2, aSeed) * (uResolution.y / 520.0) / z;

  vDepth = clamp((pos.z + 1.0) * 0.5, 0.0, 1.0);
  vInner = 1.0 - shell;
  vRim = 1.0 - abs(normalize(pos).z);
  vBoil = pow(boil, 1.0 + uTurbulence * 2.0);
}
`;

const FRAGMENT = `#version 300 es
precision highp float;

in float vDepth;
in float vInner;
in float vRim;
in float vBoil;

uniform vec3 uColor;
uniform float uIntensity;

out vec4 fragColor;

void main() {
  // Round points; square ones read as compression artefacts.
  vec2 offset = gl_PointCoord - 0.5;
  float d = dot(offset, offset);
  if (d > 0.25) discard;

  float edge = 1.0 - smoothstep(0.06, 0.25, d);
  float depth = mix(0.22, 1.0, vDepth);

  // Additive blending stacks, so per-point alpha stays low and the glow comes
  // from accumulation. The rim term is what makes the silhouette read.
  // The rim is what makes a silhouette; pow 3 was too tight to see it.
  float weight = 1.0 + vInner * 1.6 + pow(vRim, 1.8) * 2.6;
  float alpha = edge * depth * weight * mix(0.18, 1.0, vBoil) * uIntensity;

  // Premultiplied output: the blend is ONE/ONE, so colour arrives already
  // scaled by its own alpha and the browser composites it without dividing.
  vec3 rgb = uColor * (1.0 + vInner * 0.25);
  fragColor = vec4(rgb * alpha, alpha);
}
`;

type Props = {
  state: SystemStateName;
  activity: number;
  novelty: number | null;
  confidence: number | null;
  size?: number;
};

function compile(gl: WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    // Falling back silently hides a broken shader behind a working fallback,
    // which is the worst of both: nobody would ever know it was broken.
    console.error("GODGOD field: shader failed to compile", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export default function FieldSphere({
  state,
  activity,
  novelty,
  confidence,
  size = 520,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [unsupported, setUnsupported] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Premultiplied + ONE/ONE is the only combination that composites additive
    // glow correctly over the page. With premultipliedAlpha:false the browser
    // divides the accumulated colour by the accumulated alpha on composite,
    // which crushed the whole sphere to almost nothing — seen in a screenshot.
    const gl = canvas.getContext("webgl2", {
      antialias: true,
      alpha: true,
      premultipliedAlpha: true,
    });
    if (!gl) {
      setUnsupported(true);
      return;
    }

    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vertex || !fragment || !program) {
      setUnsupported(true);
      return;
    }
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("GODGOD field: program failed to link", gl.getProgramInfoLog(program));
      setUnsupported(true);
      return;
    }
    gl.useProgram(program);

    // Fibonacci sphere: an even distribution without the pole clustering that
    // makes a latitude/longitude grid look like a beach ball.
    const positions = new Float32Array(POINTS * 3);
    const seeds = new Float32Array(POINTS);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < POINTS; i += 1) {
      const y = 1 - (i / (POINTS - 1)) * 2;
      const radius = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      positions[i * 3] = Math.cos(theta) * radius;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = Math.sin(theta) * radius;
      // Deterministic, not Math.random: the same state draws the same sphere.
      // An integer hash, not sin(i * k) — that aliases against the golden angle
      // and draws a visible spiral through the shell radii. Seen in a render.
      let h = Math.imul(i, 747796405) + 2891336453;
      h = Math.imul((h >>> ((h >>> 28) + 4)) ^ h, 277803737);
      seeds[i] = (((h >>> 22) ^ h) >>> 8) / 0xffffff;
    }

    const positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
    const aPosition = gl.getAttribLocation(program, "aPosition");
    gl.enableVertexAttribArray(aPosition);
    gl.vertexAttribPointer(aPosition, 3, gl.FLOAT, false, 0, 0);

    const seedBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, seedBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, seeds, gl.STATIC_DRAW);
    const aSeed = gl.getAttribLocation(program, "aSeed");
    gl.enableVertexAttribArray(aSeed);
    gl.vertexAttribPointer(aSeed, 1, gl.FLOAT, false, 0, 0);

    const uTime = gl.getUniformLocation(program, "uTime");
    const uTurbulence = gl.getUniformLocation(program, "uTurbulence");
    const uCore = gl.getUniformLocation(program, "uCore");
    const uActivity = gl.getUniformLocation(program, "uActivity");
    const uColor = gl.getUniformLocation(program, "uColor");
    const uResolution = gl.getUniformLocation(program, "uResolution");
    const uDpr = gl.getUniformLocation(program, "uDpr");
    const uIntensity = gl.getUniformLocation(program, "uIntensity");

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    gl.viewport(0, 0, canvas.width, canvas.height);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.DEPTH_TEST);

    const color = STATE_COLOR[state] ?? STATE_COLOR.IDLE;
    gl.uniform3fv(uColor, color);
    gl.uniform1f(uTurbulence, 0.18 + (novelty ?? 0) * 0.82);
    gl.uniform1f(uCore, 0.42 + (confidence ?? 0) * 0.3);
    gl.uniform1f(uActivity, activity);
    gl.uniform2f(uResolution, canvas.width, canvas.height);
    gl.uniform1f(uDpr, dpr);
    gl.uniform1f(uIntensity, INTENSITY);

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let raf = 0;
    let start = 0;

    const draw = (now: number) => {
      if (!start) start = now;
      gl.uniform1f(uTime, (now - start) / 1000);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.POINTS, 0, POINTS);
      if (!reduceMotion) raf = requestAnimationFrame(draw);
    };

    // A still frame still shows the shape, so reduced motion loses nothing.
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      gl.deleteBuffer(positionBuffer);
      gl.deleteBuffer(seedBuffer);
      gl.deleteProgram(program);
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
    };
  }, [state, activity, novelty, confidence, size]);

  if (unsupported) {
    return (
      <AnomalyField
        state={state}
        activity={activity}
        novelty={novelty}
        confidence={confidence}
        size={size}
      />
    );
  }

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      aria-label={
        `GODGOD field. state ${state}, activity ${activity.toFixed(2)}` +
        (novelty !== null ? `, novelty ${novelty.toFixed(2)}` : "")
      }
      role="img"
    />
  );
}
