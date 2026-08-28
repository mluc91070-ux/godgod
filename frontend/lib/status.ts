import { cache } from "react";

import { api } from "@/lib/api";
import type { Status } from "@/lib/types";

/**
 * The status every page needs, fetched once per render.
 *
 * The layout asks for it twice on its own — the honesty strip and the footer —
 * and several pages ask a third time. Three identical round trips to an API on
 * the critical path of every page is three too many. `cache` memoises the call
 * for the duration of one render, so the layout and the page share a request.
 *
 * Deliberately not cached *between* renders: a status line describing the
 * system as it was a minute ago is the failure that strip exists to avoid.
 *
 * It lives here rather than in `lib/api` because `react.cache` is a Server
 * Component API, and `lib/api` is imported by client components — the live
 * terminal among them. A module that throws the moment it is evaluated in a
 * browser is not a module a client component may import.
 */
export const getStatus = cache(async () => api<Status>("/api/status"));
