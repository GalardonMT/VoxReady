import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import { resolve } from "node:path";

// El monorepo mantiene la configuración compartida en VoxReady/.env.
// Las variables del proceso conservan prioridad sobre ese archivo.
loadEnvConfig(resolve(process.cwd(), ".."), process.env.NODE_ENV !== "production");

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
