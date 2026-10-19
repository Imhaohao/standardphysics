import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  agentRules: false,
  reactStrictMode: true,
  turbopack: { root: __dirname },
};

export default nextConfig;
