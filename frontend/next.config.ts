import type { NextConfig } from "next";
import { vercelAppRedirect } from "./lib/ga4";

const nextConfig: NextConfig = {
  // Dev blocks /_next and HMR unless the document host is allowlisted.
  // Production still loads the tag only when hostname is longmuch.com.
  allowedDevOrigins: ["longmuch.com"],
  async redirects() {
    return [vercelAppRedirect()];
  },
};

export default nextConfig;
