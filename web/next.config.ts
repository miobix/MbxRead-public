import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // Static export emits e.g. out/read/index.html rather than out/read.html, which
  // is what FastAPI's StaticFiles(html=True) can actually resolve for GET /read.
  trailingSlash: true,
  async rewrites() {
    // Only applies to `next dev` — a static export has no server to rewrite with,
    // so in production the exported app is served by FastAPI on the same origin.
    return [{ source: "/api/:path*", destination: "http://localhost:8002/api/:path*" }];
  },
};

export default nextConfig;
