import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "export",
  images: {
    unoptimized: true, // Requis par Next.js pour l'exportation statique (S3 ne gère pas l'optimisation dynamique d'images)
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "9001", pathname: "/**" },
      { protocol: "http", hostname: "127.0.0.1", port: "9001", pathname: "/**" },
    ],
  },
};

export default nextConfig;