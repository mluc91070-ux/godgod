/**
 * API client.
 *
 * When the research API is unreachable the UI shows that it is unreachable.
 * It never substitutes placeholder numbers for missing data.
 *
 * Every request is bounded. Pages fetch server-side, so an API that is slow to
 * answer holds the whole render open: a sleeping free-tier instance takes 30 to
 * 60 seconds to wake, and without a deadline the page simply never arrives.
 * A visitor reads that as a broken site, which is worse than an honest one
 * saying it cannot reach its backend right now.
 */

const TIMEOUT_MS = 6000;

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

export async function api<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<ApiResult<T>> {
  const { timeoutMs = TIMEOUT_MS, ...rest } = init ?? {};
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...rest,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
      headers: { accept: "application/json", ...(rest.headers ?? {}) },
    });
    if (!response.ok) {
      return { ok: false, error: `${response.status} ${response.statusText}` };
    }
    return { ok: true, data: (await response.json()) as T };
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return {
        ok: false,
        error: `no answer within ${timeoutMs / 1000}s — the API may be waking up`,
      };
    }
    const message = error instanceof Error ? error.message : "unknown error";
    return { ok: false, error: `unreachable: ${message}` };
  }
}

export function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function fmtUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}m`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}k`;
  return `$${value.toFixed(2)}`;
}

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US");
}

export function fmtTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().replace("T", " ").slice(0, 19);
}

export function clock(value: string | null | undefined): string {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toISOString().slice(11, 19);
}
