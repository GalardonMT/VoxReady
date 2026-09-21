import type { NextConfig } from "next";
import path from "path";
import fs from "fs";
import { loadEnvConfig } from "@next/env";

// Automatically load environment variables from the project root .env if it exists
const rootDir = path.resolve(process.cwd(), "..");
if (fs.existsSync(path.join(rootDir, ".env"))) {
  loadEnvConfig(rootDir);
}

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
