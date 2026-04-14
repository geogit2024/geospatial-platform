/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Proxy /api/* to the backend at runtime (server-side env var, not baked-in at build)
  async rewrites() {
    const apiUrl = process.env.API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
