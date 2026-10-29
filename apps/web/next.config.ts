import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    process.env.LOCAL_IP || "",
    "192.168.*",
    "192.168.*.*",
    "10.*",
    "10.*.*.*",
    "172.*",
    "*.local",
    "localhost",
    "localhost:3000",
    "127.0.0.1",
    "127.0.0.1:3000",
    "*.trycloudflare.com",
  ].filter(Boolean),
  experimental: {
    proxyClientMaxBodySize: "350mb",
    serverActions: {
      bodySizeLimit: "350mb",
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
