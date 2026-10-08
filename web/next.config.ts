import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pages are prerendered and cached; the data pipeline invalidates them by tag
  // (POST /api/revalidate) when new official data is loaded.
  cacheComponents: true,
  poweredByHeader: false,
  // The repo root has its own package.json for database/map tooling; this app is self-contained.
  turbopack: { root: import.meta.dirname },
  // Neon's free tier runs out of memory if hundreds of pages query it at once during the build:
  // fewer pages in flight per worker, more pages per worker, and a retry for a transient failure.
  experimental: {
    staticGenerationMaxConcurrency: 4,
    staticGenerationMinPagesPerWorker: 60,
    staticGenerationRetryCount: 2,
  },
};

export default nextConfig;
