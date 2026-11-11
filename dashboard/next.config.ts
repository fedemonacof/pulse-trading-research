import type { NextConfig } from "next";

// Export statico in dashboard/out: lo serve FastAPI (python main.py app), un solo processo da avviare.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
