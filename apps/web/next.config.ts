import type { NextConfig } from "next";

const config: NextConfig = {
  // Sin ESLint en el build; los tipos sí se comprueban (tsc).
  eslint: { ignoreDuringBuilds: true },
  poweredByHeader: false,
};

export default config;
