import type { NextConfig } from "next";

const apiBaseUrl = process.env.API_BASE_URL ?? "http://127.0.0.1:8200";

function supabaseSources() {
  const configured = process.env.SUPABASE_URL?.trim();
  if (!configured) return [];
  try {
    const url = new URL(configured);
    const websocket = `${url.protocol === "https:" ? "wss:" : "ws:"}//${url.host}`;
    return [url.origin, websocket];
  } catch {
    return [];
  }
}

const enforcedCsp = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
].join("; ");

const reportOnlyCsp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: https:",
  `connect-src 'self' ${supabaseSources().join(" ")}`.trim(),
  "worker-src 'self' blob:",
  "frame-src 'none'",
  "manifest-src 'self'",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Docker consumes the standalone bundle. Vercel needs Next.js' native
  // output so it can split routes and functions correctly.
  output: process.env.VERCEL === "1" ? undefined : "standalone",
  experimental: {
    serverActions: {
      bodySizeLimit: "256kb",
    },
  },
  devIndicators: false,
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiBaseUrl}/api/:path*`,
      },
    ];
  },
  async headers() {
    const headers = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
      },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Content-Security-Policy", value: enforcedCsp },
      { key: "Content-Security-Policy-Report-Only", value: reportOnlyCsp },
    ];
    if (process.env.APP_ENV === "production") {
      headers.push({
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains",
      });
    }
    return [{ source: "/(.*)", headers }];
  },
};

export default nextConfig;
