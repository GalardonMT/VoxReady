import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "path";
import fs from "fs";

// Cargar variables de entorno desde VoxReady/.env si existe
const rootDir = path.resolve(process.cwd(), "..");
if (fs.existsSync(path.join(rootDir, ".env"))) {
  loadEnvConfig(rootDir);
}

const nextConfig: NextConfig = {
  output: "export",
  images: {
    unoptimized: true,
  },
  trailingSlash: true,
};

export default nextConfig;
