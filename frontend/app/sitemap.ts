import type { MetadataRoute } from "next";

const SITE = "https://godgod.vercel.app";

/** Every page that exists, listed once, so discovery does not depend on the nav. */
const ROUTES = [
  "",
  "/about",
  "/docs",
  "/token",
  "/roadmap",
  "/terminal",
  "/observe",
  "/data",
  "/hypotheses",
  "/experiments",
  "/findings",
  "/patterns",
  "/research",
  "/memory",
  "/agents",
  "/lore",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ROUTES.map((route) => ({
    url: `${SITE}${route}`,
    lastModified: now,
    changeFrequency: route === "" ? "hourly" : "daily",
    priority: route === "" ? 1 : 0.7,
  }));
}
