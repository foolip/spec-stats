import type { NextConfig } from "next";

// The site's root on its host: /spec-stats on GitHub Pages. SITE_BASE="" serves it from /.
const base = (process.env.SITE_BASE ?? "/spec-stats").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath: base,
  env: { NEXT_PUBLIC_SITE_BASE: base },
  images: { unoptimized: true },
};

export default nextConfig;
