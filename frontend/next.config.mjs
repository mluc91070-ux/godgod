/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The API base is the only runtime configuration the browser needs. No key
  // of any kind is ever exposed to the frontend.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },

  async headers() {
    // Files in public/ are served with `max-age=0, must-revalidate` by default,
    // because their names carry no content hash. For the hero video that meant
    // 830KB revalidated on every visit — a blocking round trip before anything
    // plays, on the largest asset on the site.
    //
    // A day of freshness with a week of stale-while-revalidate: repeat visits
    // are instant, and a replaced file reaches everyone within a day without
    // needing the filename to change. Long enough to matter, short enough that
    // nobody is stuck looking at an old hero.
    const media = "public, max-age=86400, stale-while-revalidate=604800";

    return [
      {
        source: "/:file(sphere\.(?:mp4|webm)|sphere-poster\.jpg)",
        headers: [{ key: "Cache-Control", value: media }],
      },
      {
        // Icons and the social card change even less often than the video.
        source: "/:file(favicon\.ico|icon\.svg|apple-icon\.png|og\.png)",
        headers: [
          { key: "Cache-Control", value: "public, max-age=604800, stale-while-revalidate=2592000" },
        ],
      },
    ];
  },
};

export default nextConfig;
