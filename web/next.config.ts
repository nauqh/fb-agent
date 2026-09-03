import type { NextConfig } from "next";

/**
 * `/api/*` is proxied to FastAPI.
 *
 * A rewrite rather than a cross-origin fetch, so the browser only ever talks to
 * one origin and there is no CORS allowlist to keep in sync on the Python side.
 * It also lets `lib/api/*` use plain relative paths.
 *
 * 127.0.0.1 and not localhost: on Windows localhost resolves to ::1 first while
 * uvicorn binds IPv4 by default, and the mismatch surfaces as ECONNREFUSED
 * against a server that is plainly running.
 */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
  experimental: {
    // Next's default is 1MB for request bodies that flow through the proxy
    // (src/proxy.ts), and everything above that comes back 413 from Next —
    // not from FastAPI, whose own cap is 200MB. CTA clips are videos.
    proxyClientMaxBodySize: "200mb",
  },
};

export default nextConfig;
