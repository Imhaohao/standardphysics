import path from "node:path";
import type { NextConfig } from "next";
import { API_ORIGIN } from "./src/lib/api-origin";

const repositoryRoot = path.join(__dirname, "..", "..");

const nextConfig: NextConfig = {
  devIndicators: false,
  allowedDevOrigins: ["*.local", "10.*.*.*", "192.168.*.*", "172.*.*.*"],
  experimental: {
    proxyTimeout: 120_000,
  },
  turbopack: {
    root: repositoryRoot,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
