import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname),
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "9001", pathname: "/**" },
      { protocol: "http", hostname: "127.0.0.1", port: "9001", pathname: "/**" },
    ],
  },
};

export default nextConfig;
