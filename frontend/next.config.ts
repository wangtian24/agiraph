import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  turbopack: {
    resolveAlias: {
      // CSS @import "tailwindcss" needs the actual CSS entry file, not the directory.
      // Without this, Turbopack's resolver walks up to the project root looking for
      // node_modules/tailwindcss and fails 2000+ times, flooding .fe.log.
      tailwindcss: path.resolve(__dirname, "node_modules/tailwindcss/index.css"),
    },
  },
};

export default nextConfig;
