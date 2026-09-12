import type { NextConfig } from "next";
import { API_ORIGIN } from "./src/lib/api-origin";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
