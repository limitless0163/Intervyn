import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@intervyn/shared"],
  // WP-12: emit a self-contained server bundle (.next/standalone) so the
  // production Docker image is a slim `node server.js` with no node_modules
  // install at runtime. Additive — does not affect `next dev` / `next start`.
  output: "standalone",
  experimental: {
    // A 10 MB CV grows by ~33% as Base64 in the storage-free setup flow.
    serverActions: { bodySizeLimit: "15mb" },
    // The auth proxy buffers Server Action requests before they reach the action.
    proxyClientMaxBodySize: "15mb",
  },
};

export default nextConfig;
