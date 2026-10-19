import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  agentRules: false,
  reactStrictMode: true,
  distDir: process.env.SP_DIST_DIR ?? ".next",
  turbopack: { root: __dirname },
};

export default nextConfig;
