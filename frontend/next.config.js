/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  // Local dev only: proxy /api/* → backend when NEXT_PUBLIC_API_URL is not set.
  // In production (Cloud Run) NEXT_PUBLIC_API_URL is baked in at build time,
  // so these rewrites are never reached.
  async rewrites() {
    if (process.env.NEXT_PUBLIC_API_URL) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.DEV_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
