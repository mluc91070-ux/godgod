import type { MetadataRoute } from "next";

const SITE = "https://godgod.vercel.app";

/**
 * There was no robots.txt and no sitemap, so the only routes anything could
 * discover were the ones linked from the homepage. Combined with a nav that
 * mounted its links on click, that left most of the site invisible to a
 * crawler — an audit reported "no deeper routes were discovered" and it was
 * an accurate description of what it had been given.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
    },
    sitemap: `${SITE}/sitemap.xml`,
  };
}
