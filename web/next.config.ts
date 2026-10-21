import path from "node:path";
import type { NextConfig } from "next";

/** The repo root, so pages can import rules/coverage.json at build time. Dependencies still resolve from web/node_modules. */
const repoRoot = path.join(__dirname, "..");

const nextConfig: NextConfig = {
  devIndicators: false,
  agentRules: false,
  reactStrictMode: true,
  distDir: process.env.SP_DIST_DIR ?? ".next",
  turbopack: { root: repoRoot },
  outputFileTracingRoot: repoRoot,
};

export default nextConfig;
