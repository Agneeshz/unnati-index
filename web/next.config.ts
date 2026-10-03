import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pages are prerendered and cached; the data pipeline invalidates them by tag
  // (POST /api/revalidate) when new official data is loaded.
  cacheComponents: true,
  poweredByHeader: false,
  // The repo root has its own package.json for database/map tooling; this app is self-contained.
  turbopack: { root: import.meta.dirname },
};

export default nextConfig;
